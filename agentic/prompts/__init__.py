"""
RedAmon Agent Prompts Package

System prompts for the ReAct agent orchestrator.
Includes phase-aware reasoning, tool descriptions, and structured output formats.
"""

# Re-export from base
from .base import (
    TOOL_REGISTRY,
    INTERNAL_TOOLS,
    MODE_DECISION_MATRIX,
    REACT_SYSTEM_PROMPT,
    PENDING_OUTPUT_ANALYSIS_SECTION,
    PHASE_TRANSITION_MESSAGE,
    USER_QUESTION_MESSAGE,
    FINAL_REPORT_PROMPT,
    CONVERSATIONAL_RESPONSE_PROMPT,
    SUMMARY_RESPONSE_PROMPT,
    determine_response_tier,
    TEXT_TO_CYPHER_SYSTEM,
    # Dynamic prompt builders
    build_tool_availability_table,
    build_informational_tool_descriptions,
    build_informational_guidance,
    build_attack_path_behavior,
    build_tool_args_section,
    build_tool_name_enum,
    build_phase_definitions,
    build_dynamic_rules,
)

# Re-export from classification
from .classification import ATTACK_PATH_CLASSIFICATION_PROMPT

# Re-export from CVE exploit prompts
from .cve_exploit_prompts import (
    CVE_EXPLOIT_TOOLS,
    CVE_PAYLOAD_GUIDANCE_STATEFULL,
    CVE_PAYLOAD_GUIDANCE_STATELESS,
    NO_MODULE_FALLBACK_STATEFULL,
    NO_MODULE_FALLBACK_STATELESS,
)

# Re-export from Hydra brute force prompts
from .brute_force_credential_guess_prompts import (
    HYDRA_BRUTE_FORCE_TOOLS,
    HYDRA_WORDLIST_GUIDANCE,
)

# Re-export from phishing / social engineering prompts
from .phishing_social_engineering_prompts import (
    PHISHING_SOCIAL_ENGINEERING_TOOLS,
    PHISHING_PAYLOAD_FORMAT_GUIDANCE,
)

# Re-export from unclassified attack path prompts
from .unclassified_prompts import UNCLASSIFIED_EXPLOIT_TOOLS

# Re-export from post-exploitation prompts
from .post_exploitation import (
    POST_EXPLOITATION_TOOLS_STATEFULL,
    POST_EXPLOITATION_TOOLS_STATELESS,
)

# Re-export from stealth rules
from .stealth_rules import STEALTH_MODE_RULES

# Import utilities
from utils import get_session_config_prompt
from project_settings import get_setting, get_allowed_tools_for_phase, get_hydra_flags_from_settings


def _msf_search_failed(execution_trace: list) -> bool:
    """Check if a Metasploit `search` command returned no results in the trace."""
    for step in execution_trace:
        if step.get("tool_name") != "metasploit_console":
            continue
        output = step.get("tool_output") or ""
        args = step.get("tool_args") or {}
        command = args.get("command", "") if isinstance(args, dict) else str(args)
        # Only match actual search commands, not other msf commands
        if "search " in command.lower() and (
            "No results" in output
            or "0 results" in output
            or "did not match" in output.lower()
        ):
            return True
    return False


def get_phase_tools(
    phase: str,
    activate_post_expl: bool = True,
    post_expl_type: str = "stateless",
    attack_path_type: str = "cve_exploit",
    execution_trace: list = None,
) -> str:
    """Get tool descriptions for the current phase with attack path-specific guidance.

    All tool references are dynamically filtered based on the DB TOOL_PHASE_MAP,
    so the LLM only sees tools that are actually allowed in the current phase.

    Args:
        phase: Current agent phase (informational, exploitation, post_exploitation)
        activate_post_expl: If True, post-exploitation phase is available.
                           If False, exploitation is the final phase.
        post_expl_type: "statefull" for Meterpreter sessions, "stateless" for single commands.
        attack_path_type: Type of attack path ("cve_exploit", "brute_force_credential_guess", "phishing_social_engineering")
        execution_trace: List of execution steps (used to detect MSF search failures).

    Returns:
        Concatenated tool descriptions appropriate for the phase, mode, and attack path.
    """
    parts = []
    is_statefull = post_expl_type == "statefull"

    # Stealth mode header — reminds LLM that stealth constraints apply to all tools below
    if get_setting('STEALTH_MODE', False):
        parts.append(
            "## STEALTH MODE ACTIVE\n\n"
            "All tools below MUST be used with stealth constraints. "
            "See STEALTH MODE rules above for per-tool restrictions.\n"
        )

    # Add phase-specific custom system prompt if configured
    informational_prompt = get_setting('INFORMATIONAL_SYSTEM_PROMPT', '')
    expl_prompt = get_setting('EXPL_SYSTEM_PROMPT', '')
    post_expl_prompt = get_setting('POST_EXPL_SYSTEM_PROMPT', '')

    if phase == "informational" and informational_prompt:
        parts.append(f"## Custom Instructions\n\n{informational_prompt}\n")
    elif phase == "exploitation" and expl_prompt:
        parts.append(f"## Custom Instructions\n\n{expl_prompt}\n")
    elif phase == "post_exploitation" and post_expl_prompt:
        parts.append(f"## Custom Instructions\n\n{post_expl_prompt}\n")

    # Determine allowed tools for current phase (dynamic from TOOL_PHASE_MAP in DB)
    # Filter out internal tools that should never be shown to the LLM
    allowed_tools = [t for t in get_allowed_tools_for_phase(phase) if t not in INTERNAL_TOOLS]

    # Dynamic tool availability table — skip in informational phase where
    # build_informational_tool_descriptions() already provides full details
    if phase != "informational":
        parts.append(build_tool_availability_table(phase, allowed_tools))

    # Add mode decision matrix for exploitation only (not needed in post-expl, mode already determined)
    if phase == "exploitation" and attack_path_type == "cve_exploit":
        # Mode context
        target_types = "Dropper/Staged/Meterpreter" if is_statefull else "Command/In-Memory/Exec"
        post_expl_note = "Interactive session commands available" if is_statefull else "Re-run exploit with different CMD values"

        parts.append(MODE_DECISION_MATRIX.format(
            mode=post_expl_type,
            target_types=target_types,
            post_expl_note=post_expl_note
        ))

    # Pre-configured payload settings (LHOST/LPORT/ngrok) — injected BEFORE attack
    # chain so the agent knows the payload direction regardless of attack path type.
    #
    # Injection conditions:
    #   1. exploitation phase + statefull mode (CVE exploit, brute force)
    #   2. phishing attack path in ANY phase — payloads are generated before
    #      exploitation (agent runs msfvenom during informational phase,
    #      and the "exploitation" in phishing IS when the target opens the file)
    needs_session_config = (
        (phase == "exploitation" and is_statefull)
        or attack_path_type == "phishing_social_engineering"
    )
    if needs_session_config:
        session_config = get_session_config_prompt()
        if session_config:
            parts.append(session_config)

    # Add phase and ATTACK PATH specific workflow guidance
    if phase == "informational":
        # Dynamic tool descriptions (only shows allowed tools)
        parts.append(build_informational_tool_descriptions(allowed_tools))

    elif phase == "exploitation":
        # SELECT WORKFLOW BASED ON ATTACK PATH TYPE
        if attack_path_type == "brute_force_credential_guess" and "execute_hydra" in allowed_tools:
            # Hydra-based brute force workflow
            hydra_flags = get_hydra_flags_from_settings()
            # Build flags without -t for templates that override thread count per protocol
            import re as _re
            hydra_flags_no_t = _re.sub(r'-t\s+\d+\s*', '', hydra_flags).strip()
            parts.append(HYDRA_BRUTE_FORCE_TOOLS.format(
                hydra_max_attempts=get_setting('HYDRA_MAX_WORDLIST_ATTEMPTS', 3),
                hydra_flags=hydra_flags,
                hydra_flags_no_t=hydra_flags_no_t
            ))
            # Add wordlist reference guide
            parts.append(HYDRA_WORDLIST_GUIDANCE)
        elif attack_path_type == "phishing_social_engineering":
            # Phishing / Social Engineering workflow
            parts.append(PHISHING_SOCIAL_ENGINEERING_TOOLS)
            parts.append(PHISHING_PAYLOAD_FORMAT_GUIDANCE)
            # Inject SMTP config only for phishing path (saves tokens for other paths)
            smtp_config = get_setting('PHISHING_SMTP_CONFIG', '')
            if smtp_config:
                parts.append(
                    f"## Pre-Configured SMTP Settings\n\n"
                    f"Use these for email delivery via execute_code (Python smtplib):\n{smtp_config}\n"
                )
        elif attack_path_type.endswith("-unclassified"):
            # Generic unclassified workflow — no specific tool workflow
            parts.append(UNCLASSIFIED_EXPLOIT_TOOLS)
        elif "metasploit_console" in allowed_tools:
            # CVE-based exploitation (default)
            parts.append(CVE_EXPLOIT_TOOLS)
            # Select payload guidance based on post_expl_type
            payload_guidance = CVE_PAYLOAD_GUIDANCE_STATEFULL if is_statefull else CVE_PAYLOAD_GUIDANCE_STATELESS
            parts.append(payload_guidance)
            # No-module fallback: only inject full workflow AFTER msf search returned no results
            # This saves ~1,100-1,350 tokens when a module IS found
            if _msf_search_failed(execution_trace or []):
                if is_statefull:
                    parts.append(NO_MODULE_FALLBACK_STATEFULL)
                else:
                    parts.append(NO_MODULE_FALLBACK_STATELESS)
        else:
            # No exploitation tools available — show only informational tool descriptions
            parts.append(build_informational_tool_descriptions(allowed_tools))

        # Add note about post-exploitation availability
        if not activate_post_expl:
            parts.append("\n**NOTE:** Post-exploitation phase is DISABLED. Complete exploitation and use action='complete'.\n")

    elif phase == "post_exploitation":
        # Only show post-exploitation workflows if metasploit_console is allowed
        if "metasploit_console" in allowed_tools:
            if is_statefull:
                parts.append(POST_EXPLOITATION_TOOLS_STATEFULL)
            else:
                parts.append(POST_EXPLOITATION_TOOLS_STATELESS)
        else:
            # metasploit_console disabled — show only informational tool descriptions
            parts.append(build_informational_tool_descriptions(allowed_tools))

    return "\n".join(parts)


# Export list for explicit imports
__all__ = [
    # Tool registry and builders
    "TOOL_REGISTRY",
    "INTERNAL_TOOLS",
    "build_tool_availability_table",
    "build_informational_tool_descriptions",
    "build_informational_guidance",
    "build_attack_path_behavior",
    "build_tool_args_section",
    "build_tool_name_enum",
    "build_phase_definitions",
    "build_dynamic_rules",
    # Base prompts
    "MODE_DECISION_MATRIX",
    "REACT_SYSTEM_PROMPT",
    "PENDING_OUTPUT_ANALYSIS_SECTION",
    "PHASE_TRANSITION_MESSAGE",
    "USER_QUESTION_MESSAGE",
    "FINAL_REPORT_PROMPT",
    "CONVERSATIONAL_RESPONSE_PROMPT",
    "SUMMARY_RESPONSE_PROMPT",
    "determine_response_tier",
    "TEXT_TO_CYPHER_SYSTEM",
    # Classification
    "ATTACK_PATH_CLASSIFICATION_PROMPT",
    # CVE exploit
    "CVE_EXPLOIT_TOOLS",
    "CVE_PAYLOAD_GUIDANCE_STATEFULL",
    "CVE_PAYLOAD_GUIDANCE_STATELESS",
    "NO_MODULE_FALLBACK_STATEFULL",
    "NO_MODULE_FALLBACK_STATELESS",
    # Hydra brute force
    "HYDRA_BRUTE_FORCE_TOOLS",
    "HYDRA_WORDLIST_GUIDANCE",
    # Phishing / Social Engineering
    "PHISHING_SOCIAL_ENGINEERING_TOOLS",
    "PHISHING_PAYLOAD_FORMAT_GUIDANCE",
    # Unclassified attack path
    "UNCLASSIFIED_EXPLOIT_TOOLS",
    # Post-exploitation
    "POST_EXPLOITATION_TOOLS_STATEFULL",
    "POST_EXPLOITATION_TOOLS_STATELESS",
    # Stealth rules
    "STEALTH_MODE_RULES",
    # Function
    "get_phase_tools",
]
