# Evolution Engine — Terminal Demo
#
# Prerequisites:
#   brew install charmbracelet/tap/vhs
#   pip install evolution-engine   (or use local .venv)
#
# Usage:
#   cd /tmp
#   git clone --depth=100 https://github.com/alpsla/codequal.git demo-repo
#   cd demo-repo
#   evo notifications dismiss    # clean slate for recording
#   vhs /path/to/evolution-engine/scripts/demo.tape
#
# Produces: demo.gif + demo.mp4 in current directory

Output demo.gif
Output demo.mp4

# Terminal appearance
Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 700
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 50ms
Set CursorBlink false

Env PATH "/Users/Shared/OpenClaw-Workspace/repos/evolution-engine/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# ── Scene 1: Install ──

Type "# Install Evolution Engine"
Enter
Sleep 500ms
Type "pip install evolution-engine"
Enter
Sleep 6s

# ── Scene 2: Check available signal sources ──

Type "clear"
Enter
Sleep 500ms
Type "# Step 1: What signals can EE detect in this repo?"
Enter
Sleep 1s
Type "evo sources ."
Enter
Sleep 8s

# ── Scene 3: Analyze — detect drift ──

Type "clear"
Enter
Sleep 500ms
Type "# Step 2: Run analysis — detect drift across all signals"
Enter
Sleep 1s
Type "evo analyze . --no-open"
Enter
Sleep 9s
Sleep 7s

# ── Scene 4: Copy the AI prompt ──

Type "clear"
Enter
Sleep 500ms
Type "# Step 3: Copy the prompt into Claude Code, Cursor, or Copilot"
Enter
Sleep 1s
Type "evo analyze . --show-prompt --no-report 2>/dev/null | tail -20"
Enter
Sleep 5s
Sleep 6s

# ── Scene 5: Verify after AI fixes the drift ──

Type "clear"
Enter
Sleep 500ms
Type "# Step 4: After your AI applies the fix — verify drift is resolved"
Enter
Sleep 1s
Type "evo analyze . --verify --no-open"
Enter
Sleep 9s
Sleep 3s

# ── Scene 6: Closing ──

Type "clear"
Enter
Sleep 500ms
Type "# Intentional change? Use: evo accept --pr or --permanent"
Enter
Sleep 2s
Type "# Detect → Fix → Verify. Your code never leaves your machine."
Enter
Sleep 1s
Type "# pip install evolution-engine  |  codequal.dev"
Enter
Sleep 4s
