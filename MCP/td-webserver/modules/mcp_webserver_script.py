"""
TouchDesigner MCP Web Server Script
Implements and handles API endpoints

This file serves as the entry point for modularized components in TouchDesigner.
Actual implementations are separated into modules within the mcp package.
"""

import traceback

try:
	import import_modules

	import_modules.setup()
except Exception as e:
	print(f"[ERROR] Failed to setup modules: {str(e)}")

from mcp.controllers.api_controller import api_controller_openapi


def onServerStart(webServerDAT):
	print("HTTP server started")
	"""Called when the web server starts"""
	print("======================================================")
	print("=========== HTTP SERVER STARTED ===========")
	print("======================================================")
	return


def onServerStop(webServerDAT):
	"""Called when the web server stops"""
	print("HTTP server stopped")
	return


def onHTTPRequest(webServerDAT, request, response):
	"""
	HTTP request handler for TouchDesigner WebServerDAT

	Args:
	    webServerDAT: Reference to the WebServer DAT
	    request: Request object from WebServer DAT
	    response: Response object to be filled and returned

	Returns:
	    Completed response object
	"""
	try:
		return api_controller_openapi.onHTTPRequest(webServerDAT, request, response)
	except Exception as e:
		print(f"MCP: Error handling request: {str(e)}")
		traceback.print_exc()

	response["statusCode"] = 500
	response["statusReason"] = "Internal Server Error"
	response["headers"] = {"Content-Type": "application/json"}
	response["body"] = '{"error": "API controller failed to handle the request"}'
	return response


try:
	from utils.logging import log_message
	from utils.types import LogLevel

	log_message("TouchDesigner MCP WebServer Script initialized", LogLevel.INFO)
except Exception:
	pass

print("TouchDesigner MCP WebServer Script (entry point) initialization completed")
