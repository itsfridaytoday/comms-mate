#!/usr/bin/env python3
"""
Comms Agent Backend Server
Handles Claude API calls for the Block Comms Agent dashboard.
Run this server, then use the Comms Agent dashboard for AI-powered copy generation.

No external dependencies required - uses only Python standard library.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error
import ssl
import re
import os

# Configuration
PORT = 3456
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Load brand contexts
BRAND_CONTEXTS_PATH = os.path.join(os.path.dirname(__file__), "brand-contexts.json")
BRAND_CONTEXTS = {}

def load_brand_contexts():
    global BRAND_CONTEXTS
    try:
        with open(BRAND_CONTEXTS_PATH, 'r') as f:
            BRAND_CONTEXTS = json.load(f)
        print(f"[Comms Agent] Loaded {len(BRAND_CONTEXTS)} brand contexts")
    except Exception as e:
        print(f"[Comms Agent] Warning: Could not load brand contexts: {e}")
        BRAND_CONTEXTS = {}

def detect_brand(text):
    """Detect which brand the copy is for based on keywords in the text."""
    text_lower = text.lower()
    
    for brand_key, brand_data in BRAND_CONTEXTS.items():
        keywords = brand_data.get('keywords', [])
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return brand_key, brand_data
    
    # Default to Block if no specific brand detected
    return 'block', BRAND_CONTEXTS.get('block', {})

def build_brand_prompt(brand_data):
    """Build brand-specific instructions for the prompt."""
    if not brand_data:
        return ""
    
    name = brand_data.get('name', 'Block')
    voice = brand_data.get('voice', {})
    rules = brand_data.get('writing_rules', [])
    use_phrases = brand_data.get('phrases_to_use', [])
    avoid_phrases = brand_data.get('phrases_to_avoid', [])
    examples = brand_data.get('example_copy', [])
    
    prompt = f"""
BRAND: {name}

VOICE & TONE:
- Tone: {voice.get('tone', '')}
- Personality: {voice.get('personality', '')}
- Audience: {voice.get('audience', '')}

WRITING RULES FOR {name.upper()}:
{chr(10).join(f"• {rule}" for rule in rules)}

PHRASES TO USE:
{', '.join(f'"{p}"' for p in use_phrases[:5])}

PHRASES TO AVOID:
{', '.join(f'"{p}"' for p in avoid_phrases[:5])}

EXAMPLE {name.upper()} COPY (match this style):
{chr(10).join(f'- "{ex}"' for ex in examples[:3])}
"""
    return prompt

# Base system prompt
BASE_SYSTEM_PROMPT = """You are a senior communications writer for Block (the company that owns Square, Cash App, Tidal, and Afterpay). You write copy that is human-first, clear, and direct.

UNIVERSAL BRAND VOICE RULES - MUST FOLLOW:
1. Human-First Communication: Write like talking to a friend. Natural, genuine language.
2. Clarity Through Simplicity: Get to the point. Short sentences. No jargon.
3. Playful Professionalism: Balance warmth with expertise.

CRITICAL - NEVER USE THESE IN ANY COPY:
❌ Outline-like conclusions: "challenges and opportunities", "looking ahead", "moving forward", "going forward", "future prospects", "remains to be seen", "as we look to the future", "in conclusion", "at the end of the day"
❌ Negative parallelisms: "not X, but Y", "not just", "not only", "less X, more Y", "it's not about", "this isn't about", "rather than", "instead of"

INSTEAD:
✓ State what something IS, not what it isn't
✓ End with action or clear next step, not reflection
✓ Use concrete details, not abstract summaries

DO:
- Use contractions (we're, you'll, it's)
- Write in active voice
- Use everyday language
- Be specific with numbers
- Address reader directly

DON'T:
- Use corporate buzzwords
- Write long, complex sentences
- Sound robotic"""


def call_claude(user_prompt, brand_context=""):
    """Call Claude API using urllib (no external dependencies)"""
    
    system_prompt = BASE_SYSTEM_PROMPT
    if brand_context:
        system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + brand_context
    
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt}
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
    }
    
    data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=data,
        headers=headers,
        method="POST"
    )
    
    # Create SSL context
    ctx = ssl.create_default_context()
    
    with urllib.request.urlopen(req, context=ctx, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
        return result["content"][0]["text"]


class CORSRequestHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok", 
                "message": "Comms Agent Server running",
                "brands_loaded": list(BRAND_CONTEXTS.keys())
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/generate":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            
            try:
                brief = json.loads(post_data.decode("utf-8"))
                
                # Detect brand from brief content
                detection_text = f"{brief.get('campaignName', '')} {brief.get('keyMessage', '')} {brief.get('supportingPoints', '')}"
                brand_key, brand_data = detect_brand(detection_text)
                brand_context = build_brand_prompt(brand_data)
                brand_name = brand_data.get('name', 'Block') if brand_data else 'Block'
                
                print(f"[Comms Agent] Detected brand: {brand_name}")
                
                # Build the user prompt from the brief
                user_prompt = f"""Write {brief.get('numVariants', 3)} different variants of copy for the following brief:

FORMAT: {brief.get('formatName', 'General')}
FORMAT STRUCTURE: {brief.get('formatStructure', 'Clear and direct')}
FORMAT TONE: {brief.get('formatTone', 'Professional')}
CHARACTER LIMIT: {brief.get('charLimit', 280)} characters max per variant

CAMPAIGN: {brief.get('campaignName', '')}
KEY MESSAGE: {brief.get('keyMessage', '')}
{f"SUPPORTING POINTS: {brief.get('supportingPoints')}" if brief.get('supportingPoints') else ''}
{f"TARGET AUDIENCE: {brief.get('audience')}" if brief.get('audience') else ''}
{f"TONE: {', '.join(brief.get('tones', []))}" if brief.get('tones') else ''}
{f"MUST INCLUDE: {brief.get('requiredElements')}" if brief.get('requiredElements') else ''}
{f"MUST AVOID: {brief.get('avoid')}" if brief.get('avoid') else ''}
{f"CALL TO ACTION: {brief.get('cta')}" if brief.get('cta') else ''}

Return ONLY a JSON array with {brief.get('numVariants', 3)} objects, each with:
- "variant": the copy text (must be under {brief.get('charLimit', 280)} characters)
- "angle": a 2-3 word description of the approach (e.g., "Direct & Bold", "Story-Led", "Data-Driven")

Example format:
[
  {{"variant": "Your copy here...", "angle": "Direct & Bold"}},
  {{"variant": "Another version...", "angle": "Warm & Personal"}}
]

Make each variant genuinely different in approach and structure. Match the {brand_name} brand voice exactly. Do not use any of the forbidden phrases."""

                # Call Claude with brand context
                print(f"[Comms Agent] Generating {brief.get('numVariants', 3)} variants for: {brief.get('campaignName', 'Untitled')}")
                response_text = call_claude(user_prompt, brand_context)
                
                # Parse JSON from response
                json_match = re.search(r'\[[\s\S]*\]', response_text)
                if json_match:
                    variants = json.loads(json_match.group())
                else:
                    raise ValueError("No JSON array found in response")
                
                print(f"[Comms Agent] ✓ Generated {len(variants)} variants for {brand_name}")
                
                # Send success response
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True, 
                    "variants": variants,
                    "brand_detected": brand_name
                }).encode())
                
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8') if e.fp else str(e)
                print(f"[Comms Agent] API Error: {e.code} - {error_body}")
                self.send_response(500)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": f"API Error: {e.code}"}).encode())
                
            except Exception as e:
                print(f"[Comms Agent] Error: {e}")
                self.send_response(500)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress default logging, we do our own
        pass


def main():
    load_brand_contexts()
    server = HTTPServer(("localhost", PORT), CORSRequestHandler)
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🚀 Comms Agent Server Running                              ║
║                                                              ║
║   URL: http://localhost:{PORT}                                ║
║   Health check: http://localhost:{PORT}/health                ║
║                                                              ║
║   Brand contexts loaded:                                     ║
║   {', '.join(BRAND_CONTEXTS.keys()) if BRAND_CONTEXTS else 'None'}
║                                                              ║
║   The Comms Agent dashboard can now generate AI copy.        ║
║   Press Ctrl+C to stop the server.                           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Comms Agent] Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
