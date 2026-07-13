"""
OpenAPI schema based API controller for TouchDesigner MCP Web Server

This controller uses the OpenAPIRouter to route requests based on the OpenAPI schema,
and converts between API models and internal data structures.
"""

import json
import traceback
from typing import Any, Optional, Protocol

import mcp
from mcp.controllers.generated_handlers import *
from mcp.controllers.openapi_router import OpenAPIRouter
from mcp.controllers.tier_policy import (
	load_tier_map,
	read_only_denial,
	read_only_enabled,
)
from utils import auth
from utils.error_handling import ErrorCategory
from utils.logging import log_message
from utils.serialization import safe_serialize
from utils.types import LogLevel, Result

# Routes reachable WITHOUT a token. Exactly one: the server-identity/health probe
# (no node/project/exec capability) so "is TD up + what version" stays graceful
# for a tokenless client. Every other route requires the Bearer token.
PUBLIC_ROUTES = {("GET", "/api/td/server/td")}


class ApiServiceProtocol(Protocol):
	"""Protocol defining the API service interface"""

	def call_node_method(
		self,
		node_path: str,
		method_name: str,
		args: list[Any] = None,
		kwargs: dict[str, Any] = None,
	) -> Result: ...

	def create_node(
		self,
		parent_path: str,
		node_type: str,
		node_name: Optional[str] = None,
		parameters: Optional[dict[str, Any]] = None,
	) -> Result: ...

	def delete_node(self, node_path: str) -> Result: ...

	def exec_script(self, script: str) -> Result: ...

	def get_td_info(self) -> Result: ...

	def get_nodes(
		self,
		parent_path: str,
		pattern: Optional[str] = None,
		include_properties: bool = False,
		limit: Optional[int] = None,
	) -> Result: ...

	def get_module_help(self, module_name: str) -> Result: ...

	def get_node_detail(self, node_path: str) -> Result: ...

	def get_node_errors(self, node_path: str) -> Result: ...

	def get_td_python_class_details(self, class_name: str) -> Result: ...

	def get_td_python_classes(self) -> Result: ...

	def update_node(self, node_path: str, properties: dict[str, Any]) -> Result: ...


class RequestProcessor:
	"""
	Responsible for processing and normalizing HTTP requests from different sources

	This class helps achieve separation of concerns by isolating request processing logic
	from the controller class, improving maintainability and testability.
	"""

	@staticmethod
	def normalize_request(
		request: dict[str, Any],
	) -> tuple[str, str, dict[str, Any], str]:
		"""
		Normalize request object to handle different request formats

		Args:
		    request: Request object that might be in different formats

		Returns:
		    Tuple containing (method, path, query_params, body)
		"""
		method = ""
		path = ""
		query_params = {}
		body = ""

		try:
			method = RequestProcessor._extract_method(request)

			path, uri_query_params = RequestProcessor._extract_path_and_query(request)
			query_params.update(uri_query_params)

			if "query" in request and isinstance(request["query"], dict):
				query_params.update(request["query"])

			if "pars" in request and isinstance(request["pars"], dict):
				log_message(
					f"Found 'pars' in request: {request['pars']}", LogLevel.DEBUG
				)
				query_params.update(request["pars"])

			body = RequestProcessor._extract_body(request)

		except Exception as e:
			log_message(f"Error during request normalization: {str(e)}", LogLevel.ERROR)
			log_message(traceback.format_exc(), LogLevel.DEBUG)

		return method, path, query_params, body

	@staticmethod
	def _extract_method(request: dict[str, Any]) -> str:
		"""Extract HTTP method from request"""
		if "method" in request and isinstance(request["method"], str):
			return request["method"].upper()
		return ""

	@staticmethod
	def _extract_path_and_query(request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
		"""Extract path and query parameters from request"""
		path = ""
		query_params = {}

		uri = request.get("uri", {})

		if isinstance(uri, dict):
			path = uri.get("path", "")
			uri_query = uri.get("query", {})
			if isinstance(uri_query, dict):
				query_params.update(uri_query)
		elif isinstance(uri, str):
			path = uri

		return path, query_params

	@staticmethod
	def _extract_body(request: dict[str, Any]) -> str:
		"""Extract body content from request"""
		body = ""

		body_content = request.get("body", "")

		if isinstance(body_content, (str, bytes)):
			body = (
				body_content
				if isinstance(body_content, str)
				else body_content.decode("utf-8", errors="replace")
			)
		elif isinstance(body_content, dict):
			body = json.dumps(body_content)

		if not body and "data" in request:
			data = request.get("data", "")
			if isinstance(data, bytes):
				body = data.decode("utf-8", errors="replace") if data else ""
			elif isinstance(data, str):
				body = data
			elif isinstance(data, dict):
				body = json.dumps(data)

		return body


class IController(Protocol):
	"""
	Controller interface for handling HTTP requests

	All controllers should implement this interface to ensure consistency across
	different controller implementations. This enforces a unified approach to
	request handling throughout the application.
	"""

	def onHTTPRequest(
		self, webServerDAT: Any, request: dict[str, Any], response: dict[str, Any]
	) -> dict[str, Any]:
		"""
		Process an HTTP request from TouchDesigner WebServerDAT

		Args:
		    webServerDAT: Reference to the WebServerDAT object
		    request: Dictionary containing request information
		    response: Dictionary for storing response information

		Returns:
		    Updated response dictionary
		"""
		...


class APIControllerOpenAPI(IController):
	"""
	API controller that uses OpenAPI schema for routing and model conversion

	Implements the IController interface for consistency with other controllers.
	"""

	def __init__(self, service: Optional[ApiServiceProtocol] = None):
		"""
		Initialize the controller with a service implementation

		Args:
		    service: Service implementation (uses default if None)
		"""
		if service is None:
			from mcp.services.api_service import api_service

			self._service = api_service
		else:
			self._service = service

		# Materialize the shared secret at boot (disk-loaded module → runs before
		# the first request), so the very first authenticated call does not 401
		# on a not-yet-created token file. See utils/auth.py.
		try:
			auth.get_expected_token()
		except Exception as e:  # noqa: BLE001 — never let auth init block boot
			log_message(f"Token init at boot failed: {e}", LogLevel.ERROR)

		self.router = OpenAPIRouter()
		self.register_handlers()

		# D3 tiering policy map (operationId -> class). Loaded once at boot; the
		# per-request flag decides whether it is consulted. Empty map + flag unset =
		# no-op (today's behavior). An empty map means the risk file was not found
		# (partial install) — surface it so read-only mode's fail-closed isn't a
		# silent mystery.
		self._tier_map = load_tier_map()
		if not self._tier_map:
			log_message(
				"Live tool-risk map is empty (MCP/live_tool_risk.json not found?); "
				"read-only mode (if enabled) will fail closed. Default-permissive "
				"mode is unaffected.",
				LogLevel.WARNING,
			)

	def _normalize_request(
		self, request: dict[str, Any]
	) -> tuple[str, str, dict[str, Any], str]:
		"""
		Normalize request object to handle different request formats

		Args:
		    request: Request object that might be in different formats

		Returns:
		    Tuple containing (method, path, query_params, body)
		"""
		return RequestProcessor.normalize_request(request)

	def onHTTPRequest(
		self, webServerDAT: Any, request: dict[str, Any], response: dict[str, Any]
	) -> dict[str, Any]:
		"""
		Handle HTTP request from TouchDesigner WebServer DAT

		Implements IController interface for consistent handling across controllers.

		Args:
		    webServerDAT: Reference to the WebServerDAT object
		    request: Dictionary containing request information
		    response: Dictionary for storing response information

		Returns:
		    Updated response dictionary
		"""

		if "headers" not in response:
			response["headers"] = {}

		# CORS: intentionally NO Access-Control-Allow-Origin. Dropping the former
		# wildcard means a browser cannot read cross-origin responses or complete
		# a preflight for the Authorization header — the cross-origin browser
		# vector is rejected. Non-browser clients (httpx) are unaffected; CORS is
		# browser-enforced, and requests still carry the Bearer token.
		response["headers"]["Content-Type"] = "application/json"

		try:
			method, path, query_params, body = self._normalize_request(request)
		except Exception as e:
			response["statusCode"] = 500
			response["statusReason"] = "Internal Server Error"
			response["data"] = json.dumps(
				{
					"success": False,
					"error": f"Request normalization error: {str(e)}",
					"errorCategory": str(ErrorCategory.INTERNAL),
				}
			)
			return response

		try:
			if method == "OPTIONS":
				response["statusCode"] = 200
				response["statusReason"] = "OK"
				response["data"] = "{}"
				return response

			# Shared-secret auth — fail closed BEFORE routing (covers the LAN
			# vector). Inside this try, so any extract/compare exception is
			# caught below and becomes a 500 (still denied). Exactly one route
			# (PUBLIC_ROUTES) is reachable tokenless for a graceful "is TD up".
			if (method, path) not in PUBLIC_ROUTES and not auth.token_matches(
				auth.token_from_request(request)
			):
				token_path = auth.default_token_path()
				log_message(
					f"401 unauthorized {method} {path} from "
					f"{request.get('clientAddress', '?')}",
					LogLevel.WARNING,
				)
				response["statusCode"] = 401
				response["statusReason"] = "Unauthorized"
				response["data"] = json.dumps(
					{
						"success": False,
						"data": None,
						"error": "Unauthorized: missing or invalid "
						"'Authorization: Bearer <token>' header.",
						"hint": (
							f"The MCP client and TouchDesigner share a secret at "
							f"{token_path}. On the same machine the client reads it "
							f"automatically (restart the client if it started before "
							f"TouchDesigner). For a remote client, copy that file's "
							f"value and set the {auth.TOKEN_ENV} env var in the MCP "
							f"client config."
						),
						"errorCategory": str(ErrorCategory.PERMISSION),
					}
				)
				return response

			# D3 authorization tiering (opt-in). Runs AFTER auth and BEFORE routing;
			# default (flag unset) is a no-op — byte-identical to today. An EARLY
			# RETURN is the only way to emit a real 4xx here (the success/error paths
			# below both coerce to HTTP 200).
			readonly_denial = self._read_only_denial(method, path)
			if readonly_denial is not None:
				log_message(
					f"403 read-only mode blocked {method} {path} from "
					f"{request.get('clientAddress', '?')}",
					LogLevel.WARNING,
				)
				response["statusCode"] = 403
				response["statusReason"] = "Forbidden"
				response["data"] = json.dumps(
					{
						"success": False,
						"data": None,
						"error": readonly_denial,
						"errorCategory": str(ErrorCategory.PERMISSION),
					}
				)
				return response

			result = self.router.route_request(method, path, query_params, body)

			# Surface a failed schema load instead of a silent 404 (no-op on a
			# healthy boot; only relevant once the Section-3 .tox rebuild ships).
			if (
				not result.get("success")
				and result.get("errorCategory") == ErrorCategory.NOT_FOUND
				and getattr(mcp, "schema_load_error", None)
			):
				result["error"] = (
					f"MCP OpenAPI schema failed to load "
					f"({mcp.schema_load_error}); CRUD/exec endpoints unavailable."
				)

			if result["success"]:
				response["statusCode"] = 200
				response["statusReason"] = "OK"
				response["data"] = json.dumps(safe_serialize(result))
			else:
				error_category = result.get("errorCategory", ErrorCategory.VALIDATION)
				response["statusCode"] = 200
				response["statusReason"] = self._get_status_reason_for_error(
					error_category
				)
				response["data"] = json.dumps(
					{
						"success": False,
						"data": None,
						"error": result["error"],
						"errorCategory": (
							str(error_category)
							if hasattr(error_category, "__str__")
							else None
						),
					}
				)

		except Exception as e:
			log_message(f"Error handling request: {e}", LogLevel.ERROR)
			log_message(traceback.format_exc(), LogLevel.DEBUG)

			response["statusCode"] = 500
			response["statusReason"] = "Internal Server Error"
			response["data"] = json.dumps(
				{
					"success": False,
					"error": f"Internal server error: {str(e)}",
					"errorCategory": str(ErrorCategory.INTERNAL),
				}
			)

		# Never log response['data'] — capture responses carry multi-MB base64
		# payloads. Log only the status and byte length.
		_data = response.get("data") or ""
		log_message(
			f"Response status: {response['statusCode']} ({len(_data)} bytes)",
			LogLevel.DEBUG,
		)
		return response

	def _read_only_denial(self, method: str, path: str) -> Optional[str]:
		"""Read-only policy checkpoint (D3). Returns a denial reason string when the
		route is blocked, else None (allowed).

		- Flag unset -> ALWAYS None (no-op; zero new friction).
		- Read-only mode (TD_BUILDER_LIVE_READONLY truthy) -> allow ONLY READ_ONLY;
		  DESTRUCTIVE **and** WRITE_CHECKPOINT are denied (an observe-only machine
		  must not accept a remote-forced disk write), and any unmatched/unclassified
		  route fails CLOSED. Resolves the operationId via the router's public
		  ``match`` (the same one routing would resolve), so parameterized read routes
		  are classified correctly. Decision logic lives in tier_policy (unit-tested).
		"""
		if not read_only_enabled():
			return None
		match = self.router.match(method, path)
		op_id = match.route.operation_id if match else None
		return read_only_denial(self._tier_map, op_id)

	def _get_status_code_for_error(self, error_category) -> int:
		"""
		Map error category to HTTP status code

		Args:
		    error_category: The error category

		Returns:
		    Appropriate HTTP status code
		"""
		if error_category == ErrorCategory.NOT_FOUND:
			return 404
		elif error_category == ErrorCategory.PERMISSION:
			return 403
		elif error_category == ErrorCategory.VALIDATION:
			return 400
		elif error_category == ErrorCategory.EXTERNAL:
			return 502
		else:
			return 500

	def _get_status_reason_for_error(self, error_category) -> str:
		"""
		Map error category to HTTP status reason

		Args:
		    error_category: The error category

		Returns:
		    Status reason text
		"""
		if error_category == ErrorCategory.NOT_FOUND:
			return "Not Found"
		elif error_category == ErrorCategory.PERMISSION:
			return "Forbidden"
		elif error_category == ErrorCategory.VALIDATION:
			return "Bad Request"
		elif error_category == ErrorCategory.EXTERNAL:
			return "Bad Gateway"
		else:
			return "Internal Server Error"

	def register_handlers(self) -> None:
		"""Register all handlers (generated + feedback)"""
		# Register generated handlers (from OpenAPI codegen)
		import mcp.controllers.generated_handlers as handlers

		for operation_id in handlers.__all__:
			handler = getattr(handlers, operation_id, None)
			if callable(handler):
				self.router.register_handler(operation_id, handler)
			else:
				log_message(f"Handler for {operation_id} not found.", LogLevel.WARNING)

		# Register feedback handlers (Network Editor MCP extension)
		self._register_feedback_handlers()

		# Register D3 session handlers (save + mutation_status)
		self._register_session_handlers()

	def _register_feedback_handlers(self) -> None:
		"""Register visual feedback handlers for Network Editor MCP"""
		try:
			from mcp.controllers.feedback_handlers import (
				captureTopOutput,
				getTopInfo,
				getCookErrors,
				getErrorSummary,
				get_feedback_routes,
			)

			# Register routes with full path information using FEEDBACK_ROUTES mapping
			feedback_routes = get_feedback_routes()
			for (method, path), handler in feedback_routes.items():
				operation_id = handler.__name__
				has_body = method.upper() in ["POST", "PUT", "PATCH"]
				self.router.register_route(method, path, operation_id, handler, has_body)

			log_message(f"Registered {len(feedback_routes)} feedback routes", LogLevel.INFO)
		except ImportError as e:
			log_message(f"Feedback handlers not available: {e}", LogLevel.WARNING)

	def _register_session_handlers(self) -> None:
		"""Register D3 session endpoints (save_td_project + get_mutation_status).

		Same dynamic-registration pattern as the feedback handlers — the OpenAPI
		codegen (generated_handlers.py / openapi.yaml / mustache) is deliberately
		untouched. The operationIds are the handler __name__s.
		"""
		try:
			from mcp.controllers.session_handlers import get_session_routes

			session_routes = get_session_routes()
			for (method, path), handler in session_routes.items():
				operation_id = handler.__name__
				has_body = method.upper() in ["POST", "PUT", "PATCH"]
				self.router.register_route(method, path, operation_id, handler, has_body)

			log_message(f"Registered {len(session_routes)} session routes", LogLevel.INFO)
		except ImportError as e:
			log_message(f"Session handlers not available: {e}", LogLevel.WARNING)


api_controller_openapi = APIControllerOpenAPI()
