"""
Expert Executor: Handles executing expert prompts using the three-step pattern.

This module provides the infrastructure for executing experts using the
Plan → Build → Self-Improve pattern defined in AGENT_INTERFACE.md.

Each expert has:
- A prompt directory with plan.md, build.md, self_improve.md files
- Reads sections: list of blackboard sections it can read
- Writes section: the blackboard section it writes to

The executor:
1. Loads the appropriate prompt file for the step
2. Assembles context from the blackboard
3. Renders the prompt with context substitution
4. Executes the step (currently stubbed for Claude Code conversations)
5. Validates the output
6. Returns the result

For now, actual LLM calls are stubbed since we're executing via Claude Code.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional
import re
import yaml
import logging

from .blackboard import Blackboard, SectionID
from .metrics import MetricsCollector
from .kb_query import KnowledgeBase, ExpertiseFiles
from .llm_executor import LLMExecutor, AnthropicExecutor, MockExecutor

logger = logging.getLogger(__name__)


StepType = Literal["plan", "build", "self_improve"]
ExpertiseMode = Literal["full", "compact"]  # full=234KB, compact=27KB Sweet 16 + Index


# Single source of truth for per-expert system-prompt role strings. Both
# ExpertExecutor._build_system_prompt and ExpertPool._query_llm read from
# here so they can't drift out of sync (H6 dedup). Keys match EXPERT_IDS in
# `META_AGENTIC_TOOL/meta_agentic/experts/__init__.py`.
EXPERT_ROLE_PROMPTS: dict[str, str] = {
    "creative_expert": (
        "You are a Creative Director specializing in real-time visual experiences. "
        "Your role is to translate artistic intent into actionable creative specifications."
    ),
    "cg_expert": (
        "You are a CG Technical Director with expertise in real-time rendering. "
        "Your role is to determine technical approaches for achieving visual goals."
    ),
    "td_designer": (
        "You are a TouchDesigner Network Designer. "
        "Your role is to design operator networks that implement technical specifications."
    ),
    "td_glsl_expert": (
        "You are a GLSL shader expert specializing in TouchDesigner. "
        "Your role is to write efficient, correct GLSL code for TOP operators."
    ),
    "td_python_expert": (
        "You are a Python expert specializing in TouchDesigner scripting. "
        "Your role is to write Python code for DAT and CHOP operators."
    ),
    "network_builder": (
        "You are a TouchDesigner build engineer. "
        "Your role is to generate valid TOX/TOE files from network designs."
    ),
    "ui_expert": (
        "You are a TouchDesigner UI / control-panel designer. "
        "Your role is to produce widget layouts, panel structures, and "
        "binding patterns ready for the network_builder to assemble."
    ),
    "critic": (
        "You are a quality assurance critic for TouchDesigner networks. "
        "Your role is to evaluate outputs against quality criteria and provide scores."
    ),
}


@dataclass
class ExpertConfig:
    """Configuration for a single expert."""
    expert_id: str
    prompt_dir: Path
    reads_sections: list[SectionID]
    writes_section: SectionID

    def __post_init__(self):
        """Validate that prompt directory exists."""
        if not self.prompt_dir.exists():
            raise ValueError(f"Prompt directory does not exist: {self.prompt_dir}")


class ExpertExecutor:
    """
    Executes expert prompts using the three-step pattern.

    Usage:
        config = EXPERT_CONFIGS["creative_expert"]
        executor = ExpertExecutor(config, blackboard, metrics)

        # Run single step
        result = executor.execute_step("plan")

        # Run full cycle
        results = executor.run_full_cycle()
    """

    def __init__(
        self,
        expert_config: ExpertConfig,
        blackboard: Blackboard,
        metrics: MetricsCollector,
        kb: Optional[KnowledgeBase] = None,
        llm_executor: Optional[LLMExecutor] = None,
        expertise_mode: ExpertiseMode = "compact"  # Default to compact (87% token reduction)
    ):
        self.config = expert_config
        self.blackboard = blackboard
        self.metrics = metrics
        self.expert_id = expert_config.expert_id
        self.kb = kb
        self.llm_executor = llm_executor
        self.expertise_mode = expertise_mode  # "compact" (27KB) or "full" (234KB)

    def load_prompt(self, step: StepType) -> str:
        """
        Load the prompt file for a specific step.

        Args:
            step: Which step to load ("plan", "build", or "self_improve")

        Returns:
            The raw prompt content as a string

        Raises:
            FileNotFoundError: If the prompt file doesn't exist
        """
        prompt_file = self.config.prompt_dir / f"{step}.md"

        if not prompt_file.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_file} for expert {self.expert_id}"
            )

        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    def load_expertise_for_expert(self) -> dict:
        """
        Load relevant KB expertise files based on expert_id.

        Respects expertise_mode:
            - "full": Load td_operators.yaml (234KB, ~68K tokens)
            - "compact": Load td_operators_v2.yaml (27KB, ~8.5K tokens, Sweet 16 + Index)

        Returns:
            Dictionary mapping expertise file names to their content
        """
        if self.kb is None:
            return {}

        expertise = {}

        # Select operator file based on mode
        operators_file = (
            ExpertiseFiles.OPERATORS_V2 if self.expertise_mode == "compact"
            else ExpertiseFiles.OPERATORS
        )

        # Map expert_id to relevant expertise files
        expertise_mapping = {
            "creative_expert": [ExpertiseFiles.CREATIVE_VISION],
            "cg_expert": [ExpertiseFiles.CG_CONCEPTS, operators_file],
            "td_designer": [
                operators_file,
                ExpertiseFiles.PATTERNS,
                ExpertiseFiles.PARAMETERS
            ],
            "td_glsl_expert": [ExpertiseFiles.GLSL],
            "td_python_expert": [ExpertiseFiles.PYTHON],
            "network_builder": [
                ExpertiseFiles.NETWORK_BUILDING,
                ExpertiseFiles.FILE_FORMATS
            ],
            "critic": [ExpertiseFiles.CRITIQUE_PATTERNS],
        }

        # Get the expertise files for this expert
        files_to_load = expertise_mapping.get(self.expert_id, [])

        logger.info(f"Loading expertise for {self.expert_id} (mode={self.expertise_mode}): {[f.value for f in files_to_load]}")

        for expertise_file in files_to_load:
            try:
                content = self.kb.load_expertise(expertise_file.value)
                expertise[expertise_file.value] = content
            except Exception as e:
                # Log error but continue - expertise is optional
                # Note: Using module-level logger (defined at top of file)
                logger.warning(
                    f"Failed to load expertise {expertise_file.value} for {self.expert_id}: {e}"
                )

        return expertise

    def prepare_context(self) -> dict:
        """
        Assemble context from the blackboard for this expert.

        Reads the sections specified in the expert config and prepares
        them for prompt rendering.

        Returns:
            Context dictionary with blackboard sections and metadata
        """
        context = {
            "expert_id": self.expert_id,
            "phase": self.blackboard.current_phase.value,
            "iteration": self.blackboard.iteration,
            "blackboard_sections": {},
            "current_state": {
                "phase": self.blackboard.current_phase.value,
                "iteration": self.blackboard.iteration,
                "blocking_issues": [
                    {
                        "id": i.id,
                        "section": i.section.value,
                        "severity": i.severity,
                        "description": i.description
                    }
                    for i in self.blackboard.get_unresolved_issues()
                ]
            }
        }

        # Load sections this expert can read
        for section_id in self.config.reads_sections:
            section = self.blackboard.sections[section_id]
            content = section.current_content

            # Convert to YAML string for prompt insertion
            content_yaml = yaml.dump(
                content,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            ) if content else ""

            context["blackboard_sections"][section_id.value] = {
                "content": content,
                "content_yaml": content_yaml,
                "version": section.version_count - 1 if section.versions else -1,
                "score": section.current.score if section.current else None,
                "locked": section.locked
            }

        # Load expertise from KB if available
        expertise = self.load_expertise_for_expert()
        if expertise:
            # Convert expertise to YAML strings for prompt insertion
            expertise_yaml = {}
            for file_name, content in expertise.items():
                expertise_yaml[file_name] = yaml.dump(
                    content,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False
                )

            context["expertise"] = {
                "raw": expertise,
                "yaml": expertise_yaml
            }

        return context

    def render_prompt(self, step: StepType, context: dict) -> str:
        """
        Render the prompt with context substitution.

        Loads the prompt template and substitutes placeholders with
        values from the context.

        Common placeholders:
            {{expert_name}} - The expert's ID
            {{user_request}} - Original user prompt
            {{phase}} - Current workflow phase
            {{iteration}} - Current iteration number
            {{section_content}} - Content from blackboard sections
            {{expertise_yaml}} - KB expertise as YAML

        Args:
            step: Which step to render
            context: Context dictionary from prepare_context()

        Returns:
            Rendered prompt ready for LLM
        """
        prompt_template = self.load_prompt(step)

        # Build substitution map
        substitutions = {
            "expert_name": self.expert_id,
            "expert_id": self.expert_id,
            "phase": context["phase"],
            "iteration": str(context["iteration"]),
        }

        # Add blackboard section content
        for section_name, section_data in context["blackboard_sections"].items():
            # Add YAML version for embedding in prompts
            substitutions[f"{section_name}_yaml"] = section_data["content_yaml"]

            # Add raw content version
            if section_data["content"]:
                for key, value in section_data["content"].items():
                    substitutions[f"{section_name}.{key}"] = str(value)

        # Extract user request if available
        req_section = context["blackboard_sections"].get("§1_requirements", {})
        if req_section and req_section.get("content"):
            req_content = req_section["content"]
            substitutions["user_request"] = req_content.get("original_prompt", "")
            substitutions["original_prompt"] = req_content.get("original_prompt", "")

        # Add expertise content if available
        if "expertise" in context:
            expertise_yaml = context["expertise"]["yaml"]

            # Add all expertise files as YAML
            for file_name, yaml_content in expertise_yaml.items():
                # Create a key from the file name (e.g., td_operators.yaml -> td_operators_yaml)
                key = file_name.replace(".yaml", "_yaml").replace(".yml", "_yaml")
                substitutions[key] = yaml_content

            # Also provide a combined expertise_yaml with all files
            combined_expertise = "\n\n".join([
                f"# {file_name}\n{yaml_content}"
                for file_name, yaml_content in expertise_yaml.items()
            ])
            substitutions["expertise_yaml"] = combined_expertise

        # Perform substitution
        rendered = prompt_template
        for key, value in substitutions.items():
            # Handle both {{key}} and {key} patterns
            rendered = rendered.replace("{{" + key + "}}", str(value))
            rendered = rendered.replace("{" + key + "}", str(value))

        return rendered

    def execute_step(self, step: StepType) -> dict:
        """
        Execute a single step of the expert cycle.

        This method:
        1. Prepares context from blackboard
        2. Renders the prompt
        3. Calls the LLM (currently stubbed)
        4. Validates the output
        5. Returns the result

        Args:
            step: Which step to execute ("plan", "build", or "self_improve")

        Returns:
            Dictionary with:
                - expert_id: str
                - step: str
                - prompt: str (rendered prompt)
                - output: dict (parsed output from LLM)
                - validation_errors: list[str]
                - success: bool
        """
        # Prepare context and render prompt
        context = self.prepare_context()
        rendered_prompt = self.render_prompt(step, context)

        # Execute LLM (real or stub depending on configuration)
        output = self._execute_llm(step, context, rendered_prompt)

        # Validate output
        validation_errors = self.validate_output(output)

        result = {
            "expert_id": self.expert_id,
            "step": step,
            "prompt": rendered_prompt,
            "output": output,
            "validation_errors": validation_errors,
            "success": len(validation_errors) == 0
        }

        # Record metrics
        self.metrics.record_iteration(self.blackboard.current_phase.value)

        return result

    def run_full_cycle(self) -> dict:
        """
        Run the complete Plan → Build → Self-Improve cycle.

        Returns:
            Dictionary with results from all three steps:
                - plan: dict (result from plan step)
                - build: dict (result from build step)
                - self_improve: dict (result from self_improve step)
                - final_output: dict (the final expert output)
                - overall_success: bool
                - tokens_in: int (total input tokens used)
                - tokens_out: int (total output tokens used)
        """
        results = {}
        total_tokens_in = 0
        total_tokens_out = 0

        # Track tokens from LLM executor
        def track_tokens():
            nonlocal total_tokens_in, total_tokens_out
            if self.llm_executor and hasattr(self.llm_executor, 'get_token_usage'):
                usage = self.llm_executor.get_token_usage()
                total_tokens_in += usage.get('input_tokens', 0)
                total_tokens_out += usage.get('output_tokens', 0)

        # Step 1: Plan
        plan_result = self.execute_step("plan")
        track_tokens()
        results["plan"] = plan_result

        if not plan_result["success"]:
            return {
                **results,
                "final_output": None,
                "overall_success": False,
                "failure_step": "plan",
                "tokens_in": total_tokens_in,
                "tokens_out": total_tokens_out
            }

        # Step 2: Build
        build_result = self.execute_step("build")
        track_tokens()
        results["build"] = build_result

        if not build_result["success"]:
            return {
                **results,
                "final_output": None,
                "overall_success": False,
                "failure_step": "build",
                "tokens_in": total_tokens_in,
                "tokens_out": total_tokens_out
            }

        # Step 3: Self-Improve
        self_improve_result = self.execute_step("self_improve")
        track_tokens()
        results["self_improve"] = self_improve_result

        # Determine final output
        # If self-improve provided revised output, use that
        # Otherwise, use build output
        self_improve_output = self_improve_result.get("output", {})
        final_output = self_improve_output.get(
            "revised_output",
            build_result.get("output", {})
        )

        # Normalize final_output - extract content from nested 'plan' or 'build' keys if present
        if final_output and isinstance(final_output, dict):
            # If the output is wrapped in 'plan' or 'build', extract it
            for key in ["plan", "build"]:
                if key in final_output and isinstance(final_output[key], dict):
                    # Merge the nested content to top level
                    nested = final_output[key]
                    final_output = {**final_output, **nested}
                    break

        # Check if self-improve recommends iteration
        recommendation = self_improve_output.get("recommendation", {})
        should_iterate = recommendation.get("action") == "iterate"

        return {
            **results,
            "final_output": final_output,
            "overall_success": self_improve_result["success"] and not should_iterate,
            "should_iterate": should_iterate,
            "recommendation": recommendation,
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out
        }

    def validate_output(self, output: dict) -> list[str]:
        """
        Validate expert output for common issues.

        Checks for:
        - Empty output
        - Missing required fields
        - Hallucination indicators

        Args:
            output: The output dictionary to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not output:
            errors.append("Output is empty")
            return errors

        # Check for common hallucination patterns
        output_str = str(output).lower()

        # Check for invented operators (common patterns)
        if "operator" in output_str or "top" in output_str or "chop" in output_str:
            # Look for suspicious patterns that might indicate hallucination
            suspicious_patterns = [
                r"custom\s+operator",
                r"new\s+operator",
                r"imaginary\s+operator",
                r"hypothetical\s+operator"
            ]

            for pattern in suspicious_patterns:
                if re.search(pattern, output_str):
                    errors.append(f"Possible hallucination detected: {pattern}")

        # Expert-specific validation
        if self.expert_id == "creative_expert":
            errors.extend(self._validate_creative_output(output))
        elif self.expert_id == "cg_expert":
            errors.extend(self._validate_cg_output(output))
        elif self.expert_id == "td_designer":
            errors.extend(self._validate_td_designer_output(output))

        return errors

    def _validate_creative_output(self, output: dict) -> list[str]:
        """Validate creative expert output."""
        errors = []

        # Check for required creative spec fields
        # The prompt tells the LLM to output under 'plan:' key, so check nested
        valid_keys = ["creative_spec", "mood", "plan", "creative_vision", "vision"]

        # Check root level
        has_valid_root = any(key in output for key in valid_keys)

        # Check nested under 'plan' key
        has_nested_mood = False
        plan_data = output.get("plan", {})
        if isinstance(plan_data, dict):
            has_nested_mood = "mood" in plan_data or "creative_spec" in plan_data

        if has_valid_root or has_nested_mood:
            # Valid creative output structure
            pass
        else:
            errors.append("Creative output missing 'creative_spec', 'mood', or 'plan' field")

        return errors

    def _validate_cg_output(self, output: dict) -> list[str]:
        """Validate CG expert output."""
        errors = []

        # Check for technical approach structure
        # The prompt tells the LLM to output under 'plan:' key, so check nested
        valid_keys = ["technical_approach", "techniques", "plan", "algorithm_selection", "data_flow"]

        # Check root level
        has_valid_root = any(key in output for key in valid_keys)

        # Check nested under 'plan' key
        has_nested = False
        plan_data = output.get("plan", {})
        if isinstance(plan_data, dict):
            has_nested = any(key in plan_data for key in ["algorithm_selection", "data_flow", "technical_approach"])

        if has_valid_root or has_nested:
            # Valid technical output structure
            pass
        else:
            errors.append("Technical output missing 'technical_approach', 'plan', or 'algorithm_selection' field")

        return errors

    def _validate_td_designer_output(self, output: dict) -> list[str]:
        """Validate TD Designer output."""
        errors = []

        # Check for network design structure
        # The prompt tells the LLM to output under 'plan:' or 'build:' keys
        valid_keys = ["network_design", "network", "plan", "build", "operators", "containers", "connections"]

        # Check root level
        has_valid_root = any(key in output for key in valid_keys)

        # Check nested under 'plan' or 'build' key
        has_nested = False
        for root_key in ["plan", "build"]:
            nested_data = output.get(root_key, {})
            if isinstance(nested_data, dict):
                has_nested = has_nested or any(key in nested_data for key in ["network_design", "operators", "containers"])

        if has_valid_root or has_nested:
            # Valid network design structure
            pass
        else:
            errors.append("Network design output missing 'network_design', 'operators', or 'plan' field")

        return errors

    def _execute_llm(self, step: StepType, context: dict, rendered_prompt: str) -> dict:
        """
        Execute LLM call using the configured executor.

        If llm_executor is set, makes a real API call.
        Otherwise returns stub data for testing/Claude Code execution.

        Args:
            step: The current step
            context: The execution context
            rendered_prompt: The fully rendered prompt to send

        Returns:
            Output dictionary from LLM or stub
        """
        # If no executor configured, return stub
        if self.llm_executor is None:
            logger.debug(f"No LLM executor configured, returning stub for {self.expert_id}/{step}")
            return self._stub_response(step, context)

        try:
            # Build system prompt based on expert role
            system_prompt = self._build_system_prompt()

            logger.info(f"Executing LLM call for {self.expert_id}/{step}")

            # Execute the LLM call
            response_text = self.llm_executor.execute(
                prompt=rendered_prompt,
                system=system_prompt
            )

            # Track token usage in metrics
            if hasattr(self.llm_executor, 'get_token_usage'):
                usage = self.llm_executor.get_token_usage()
                self.metrics.record_tokens(
                    input_tokens=usage.get('input_tokens', 0),
                    output_tokens=usage.get('output_tokens', 0)
                )

            # Parse the response
            output = self._parse_llm_response(response_text, step)

            logger.info(f"LLM call successful for {self.expert_id}/{step}")
            return output

        except Exception as e:
            logger.error(f"LLM execution failed for {self.expert_id}/{step}: {e}")
            return {
                "expert": self.expert_id,
                "step": step,
                "status": "error",
                "error": str(e),
                "recommendation": {
                    "action": "retry",
                    "reason": f"LLM execution failed: {e}"
                }
            }

    def _build_system_prompt(self) -> str:
        """Build the system prompt based on expert role."""
        base_prompt = EXPERT_ROLE_PROMPTS.get(
            self.expert_id,
            f"You are the {self.expert_id} expert."
        )

        # Critic needs special output format with review/score structure
        if self.expert_id == "critic":
            return (
                f"{base_prompt}\n\n"
                "CRITICAL OUTPUT FORMAT REQUIREMENT:\n"
                "You MUST output your response as valid YAML wrapped in ```yaml code blocks.\n"
                "Do NOT include any text before or after the YAML block.\n"
                "Do NOT explain what you're going to do - just output the YAML.\n\n"
                "Your output MUST follow this exact structure:\n"
                "```yaml\n"
                "review:\n"
                "  expert: critic\n"
                "  overall_score:\n"
                "    value: 0.XX  # Float between 0.0 and 1.0\n"
                "    threshold: 0.65\n"
                "    passed: true  # or false\n"
                "  decision:\n"
                "    outcome: approve  # or revise or fail\n"
                "    rationale: \"Brief explanation\"\n"
                "  feedback:\n"
                "    strengths:\n"
                "      - \"What works well\"\n"
                "    issues:\n"
                "      - severity: low  # or medium or high\n"
                "        description: \"What needs improvement\"\n"
                "```\n\n"
                "IMPORTANT: The overall_score.value MUST be a number between 0.0 and 1.0."
            )

        return (
            f"{base_prompt}\n\n"
            "CRITICAL OUTPUT FORMAT REQUIREMENT:\n"
            "You MUST output your response as valid YAML wrapped in ```yaml code blocks.\n"
            "Do NOT include any text before or after the YAML block.\n"
            "Do NOT explain what you're going to do - just output the YAML.\n\n"
            "Example format:\n"
            "```yaml\n"
            "plan:\n"
            "  expert: \"your_expert_id\"\n"
            "  task: \"description\"\n"
            "  # ... rest of your structured output\n"
            "```\n\n"
            "Be precise, avoid hallucinating operators or parameters that don't exist in TouchDesigner."
        )

    def _parse_llm_response(self, response_text: str, step: StepType) -> dict:
        """
        Parse the LLM response text into structured output.

        Args:
            response_text: Raw response from LLM
            step: The step that generated this response

        Returns:
            Parsed output dictionary
        """
        try:
            # Try to parse YAML from the response
            if hasattr(self.llm_executor, 'parse_yaml_response'):
                parsed = self.llm_executor.parse_yaml_response(response_text)
                return {
                    "expert": self.expert_id,
                    "step": step,
                    "status": "success",
                    **parsed
                }
            else:
                # Manual YAML extraction
                import re
                yaml_pattern = r"```(?:yaml|yml)\s*\n(.*?)\n```"
                matches = re.findall(yaml_pattern, response_text, re.DOTALL | re.IGNORECASE)

                if matches:
                    parsed = yaml.safe_load(matches[0])
                    return {
                        "expert": self.expert_id,
                        "step": step,
                        "status": "success",
                        **parsed
                    }
                else:
                    # Try parsing entire response as YAML
                    parsed = yaml.safe_load(response_text)
                    return {
                        "expert": self.expert_id,
                        "step": step,
                        "status": "success",
                        **parsed
                    }

        except Exception as e:
            logger.warning(f"Failed to parse YAML response: {e}")
            # Return raw response if parsing fails
            return {
                "expert": self.expert_id,
                "step": step,
                "status": "parse_warning",
                "raw_response": response_text,
                "parse_error": str(e)
            }

    def _stub_response(self, step: StepType, context: dict) -> dict:
        """
        Generate stub response for testing/Claude Code execution.

        Args:
            step: The current step
            context: The execution context

        Returns:
            Stub output dictionary
        """
        return {
            "expert": self.expert_id,
            "step": step,
            "status": "stub",
            "message": (
                f"LLM call stub for {self.expert_id} - {step} step. "
                "Configure llm_executor for real API calls."
            ),
            "recommendation": {
                "action": "proceed",
                "reason": "Stub execution"
            }
        }


# Expert configurations mapping expert_id to ExpertConfig
# This defines all available experts and their section access
def _get_expert_configs_dict() -> dict[str, ExpertConfig]:
    """
    Build the EXPERT_CONFIGS dictionary.

    This function constructs the configuration for all experts based on
    the structure defined in AGENT_INTERFACE.md.
    """
    # Base path for experts
    base_path = Path(__file__).parent.parent / "experts"

    configs = {
        "creative_expert": ExpertConfig(
            expert_id="creative_expert",
            prompt_dir=base_path / "creative_expert",
            reads_sections=[SectionID.REQUIREMENTS],
            writes_section=SectionID.CREATIVE_VISION
        ),

        "cg_expert": ExpertConfig(
            expert_id="cg_expert",
            prompt_dir=base_path / "cg_expert",
            reads_sections=[
                SectionID.REQUIREMENTS,
                SectionID.CREATIVE_VISION
            ],
            writes_section=SectionID.TECHNICAL_APPROACH
        ),

        "critic": ExpertConfig(
            expert_id="critic",
            prompt_dir=base_path / "critic",
            reads_sections=[
                SectionID.REQUIREMENTS,
                SectionID.CREATIVE_VISION,
                SectionID.TECHNICAL_APPROACH,
                SectionID.AVAILABLE_RESOURCES,
                SectionID.NETWORK_DESIGN
            ],
            writes_section=SectionID.VALIDATION_HISTORY
        ),

        "td_designer": ExpertConfig(
            expert_id="td_designer",
            prompt_dir=base_path / "td_designer",
            reads_sections=[
                SectionID.REQUIREMENTS,
                SectionID.CREATIVE_VISION,
                SectionID.TECHNICAL_APPROACH,
                SectionID.AVAILABLE_RESOURCES
            ],
            writes_section=SectionID.NETWORK_DESIGN
        ),

        "td_glsl_expert": ExpertConfig(
            expert_id="td_glsl_expert",
            prompt_dir=base_path / "td_glsl_expert",
            reads_sections=[
                SectionID.TECHNICAL_APPROACH,
                SectionID.NETWORK_DESIGN
            ],
            writes_section=SectionID.NETWORK_DESIGN  # Updates GLSL nodes
        ),

        "network_builder": ExpertConfig(
            expert_id="network_builder",
            prompt_dir=base_path / "network_builder",
            reads_sections=[SectionID.NETWORK_DESIGN],
            writes_section=SectionID.BUILD_ARTIFACTS
        ),

        "summary_generator": ExpertConfig(
            expert_id="summary_generator",
            prompt_dir=base_path / "summary_generator",
            reads_sections=[
                SectionID.NETWORK_DESIGN,
                SectionID.BUILD_ARTIFACTS
            ],
            writes_section=SectionID.BUILD_ARTIFACTS  # Adds documentation
        ),

        "td_python_expert": ExpertConfig(
            expert_id="td_python_expert",
            prompt_dir=base_path / "td_python_expert",
            reads_sections=[
                SectionID.TECHNICAL_APPROACH,
                SectionID.NETWORK_DESIGN
            ],
            writes_section=SectionID.NETWORK_DESIGN  # Updates Python nodes
        ),
    }

    return configs


# Global expert configurations
EXPERT_CONFIGS = _get_expert_configs_dict()


def get_expert_executor(
    expert_id: str,
    blackboard: Blackboard,
    metrics: MetricsCollector,
    kb: Optional[KnowledgeBase] = None,
    llm_executor: Optional[LLMExecutor] = None,
    expertise_mode: ExpertiseMode = "compact"  # Default to compact
) -> ExpertExecutor:
    """
    Create an ExpertExecutor for the specified expert.

    Args:
        expert_id: ID of the expert to execute
        blackboard: Blackboard instance
        metrics: Metrics collector instance
        kb: Optional KnowledgeBase instance for expertise access
        llm_executor: Optional LLM executor for making API calls
        expertise_mode: "full" (234KB) or "compact" (27KB Sweet 16 + Index)

    Returns:
        ExpertExecutor configured for the expert

    Raises:
        ValueError: If expert_id is not recognized
    """
    if expert_id not in EXPERT_CONFIGS:
        available = ", ".join(EXPERT_CONFIGS.keys())
        raise ValueError(
            f"Unknown expert: {expert_id}. "
            f"Available experts: {available}"
        )

    config = EXPERT_CONFIGS[expert_id]
    return ExpertExecutor(config, blackboard, metrics, kb, llm_executor, expertise_mode)


def execute_expert(
    expert_id: str,
    blackboard: Blackboard,
    metrics: MetricsCollector,
    step: Optional[StepType] = None,
    kb: Optional[KnowledgeBase] = None,
    llm_executor: Optional[LLMExecutor] = None,
    expertise_mode: ExpertiseMode = "compact"  # Default to compact
) -> dict:
    """
    Execute an expert (single step or full cycle).

    Convenience function for executing experts. If step is provided,
    executes only that step. Otherwise, runs the full cycle.

    Args:
        expert_id: ID of the expert to execute
        blackboard: Blackboard instance
        metrics: Metrics collector instance
        step: Optional specific step to execute. If None, runs full cycle.
        kb: Optional KnowledgeBase instance for expertise access
        llm_executor: Optional LLM executor for making API calls
        expertise_mode: "full" (234KB) or "compact" (27KB Sweet 16 + Index)

    Returns:
        Result dictionary from execute_step() or run_full_cycle()

    Example:
        # Run full cycle (stub mode)
        result = execute_expert("creative_expert", bb, metrics)

        # Run single step
        result = execute_expert("creative_expert", bb, metrics, step="plan")

        # With knowledge base
        result = execute_expert("td_designer", bb, metrics, kb=kb)

        # With real LLM execution
        llm = AnthropicExecutor()
        result = execute_expert("td_designer", bb, metrics, kb=kb, llm_executor=llm)

        # With compact expertise (87% token reduction)
        result = execute_expert("td_designer", bb, metrics, kb=kb, expertise_mode="compact")
    """
    executor = get_expert_executor(expert_id, blackboard, metrics, kb, llm_executor, expertise_mode)

    if step:
        return executor.execute_step(step)
    else:
        return executor.run_full_cycle()
