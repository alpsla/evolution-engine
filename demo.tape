# Evolution Engine — Terminal Demo
# Record with: vhs demo.tape
# Install VHS: brew install charmbracelet/tap/vhs
#
# Prerequisites:
#   - pip install evolution-engine (v0.3.0+)
#   - Run inside a git repo with 20+ commits (e.g. clone fastapi)
#   - Optional: GITHUB_TOKEN for CI/deployment families

# --- Output settings ---
Output demo.gif
Output demo.mp4

Set FontSize 18
Set FontFamily "JetBrains Mono"
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 60ms
Set Shell "bash"

# --- Scene 1: Install (5s) ---
# Text overlay not natively supported in VHS — add in post or use comments
# OVERLAY: "Install in 10 seconds"

Type "pip install evolution-engine"
Enter
Sleep 3s

# Simulate fast install (VHS records real output)
# If you want to fake it: comment out the pip line above
# and use Type + Enter to show a pre-recorded output

Sleep 2s

# --- Scene 2: First Run (15s) ---
# OVERLAY: "Analyze any repo"

Type "cd my-project && evo analyze ."
Enter
Sleep 12s

# Wait for pipeline to finish — adjust timing based on repo size
Sleep 3s

# --- Scene 3: Findings (20s) ---
# OVERLAY: "Detects drift before it breaks things"
# The advisory output from evo analyze is already on screen
# Give the viewer time to read

Sleep 5s

# --- Scene 4: HTML Report (10s) ---
# OVERLAY: "Interactive report with one-click actions"

Type "evo report . --open"
Enter
Sleep 5s

# Browser opens — VHS won't capture browser, just the CLI
Sleep 3s

# --- Scene 5: Sources (10s) ---
# OVERLAY: "See what data is available"

Type "evo sources ."
Enter
Sleep 6s

# --- Scene 6: Verify (10s) ---
# OVERLAY: "Track resolution over time"

Type "evo analyze . --verify"
Enter
Sleep 10s

# --- Scene 7: Closing (5s) ---
# OVERLAY: pip install evolution-engine | codequal.dev

Type "# Free — your code never leaves your machine"
Enter
Type "# pip install evolution-engine"
Enter
Type "# codequal.dev"
Enter
Sleep 4s
