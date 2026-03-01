# Evolution Engine — Scripted Terminal Demo (polished)
#
# This version produces perfect output every time using demo_output.sh.
# Best for README GIF and marketing materials.
#
# Record with: vhs demo_scripted.tape
# Install VHS: brew install charmbracelet/tap/vhs

Output demo.gif
Output demo.mp4

Set FontSize 18
Set FontFamily "JetBrains Mono"
Set Width 1000
Set Height 650
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 50ms
Set Shell "bash"

# --- Scene 1: Install (5s) ---

Sleep 1s
Type "pip install evolution-engine"
Enter
Sleep 1s
Hide
Type "bash scripts/demo_output.sh install"
Enter
Sleep 1s
Show
Sleep 3s

# --- Scene 2: Analyze (20s) ---

Type "cd my-project"
Enter
Sleep 0.5s

Type "evo analyze ."
Enter
Sleep 0.5s
Hide
Type "bash scripts/demo_output.sh analyze"
Enter
Sleep 1s
Show
Sleep 8s

# --- Scene 3: Report (8s) ---

Type "evo report . --open"
Enter
Sleep 0.5s
Hide
Type "bash scripts/demo_output.sh report"
Enter
Sleep 0.5s
Show
Sleep 4s

# --- Scene 4: Investigate (12s) ---

Type "evo investigate ."
Enter
Sleep 0.5s
Hide
Type "bash scripts/demo_output.sh investigate"
Enter
Sleep 1s
Show
Sleep 8s

# --- Scene 5: Verify (10s) ---

Type "evo analyze . --verify"
Enter
Sleep 0.5s
Hide
Type "bash scripts/demo_output.sh verify"
Enter
Sleep 1s
Show
Sleep 6s

# --- Scene 6: Closing (5s) ---

Sleep 1s
Type "# pip install evolution-engine"
Enter
Type "# codequal.dev"
Enter
Type "# Free — your code never leaves your machine"
Enter
Sleep 4s
