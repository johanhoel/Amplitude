-- Opens the installer (Contents/Resources/install.command) in Terminal, where it shows its progress.
on run
	set installer to (POSIX path of (path to me)) & "Contents/Resources/install.command"
	do shell script "open -a Terminal " & quoted form of installer
end run
