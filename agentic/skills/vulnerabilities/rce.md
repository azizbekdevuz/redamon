# RCE Testing Framework Summary

This comprehensive guide addresses remote code execution through multiple attack vectors. Key focus areas include:

**Primary Attack Surfaces:**
The document identifies four main RCE pathways: OS command execution, dynamic evaluation systems, insecure deserialization, and media pipeline vulnerabilities. Additionally, it covers SSRF chains and container escalation techniques.

**Detection Methods:**
The framework emphasizes "quiet, portable oracles" rather than noisy exploitation. Time-based detection uses commands like `sleep` on Unix or `timeout` on Windows, while out-of-band techniques leverage DNS and HTTP callbacks for confirmation.

**Command Injection Techniques:**
Beyond simple delimiters (`;`, `|`, `&&`), the guide covers argument injection, path confusion, and evasion through whitespace manipulation, token splitting, and base64 encoding to bypass filters.

**Template and Serialization Vulnerabilities:**
Specific payloads are provided for engines like Jinja2, Twig, and Freemarker, along with gadget chain exploitation via ysoserial for Java deserialization attacks.

**Specialized Vectors:**
The document highlights often-overlooked sinks including ImageMagick, Ghostscript, ExifTool, and LaTeX as legitimate code execution pathways, plus container-specific techniques targeting Docker and Kubernetes environments.

**Validation Standards:**
Reliable proof requires demonstrable command execution with controlled output, context confirmation, and persistence evidence—avoiding false positives from crashes or timeouts alone.
