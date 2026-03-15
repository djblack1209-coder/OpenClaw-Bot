on _read_secret(serviceName)
  try
    return do shell script "security find-generic-password -s " & quoted form of serviceName & " -a 'default' -w"
  on error
    return ""
  end try
end _read_secret

set ibUser to _read_secret("clawbot.ibkr.username")
set ibPass to _read_secret("clawbot.ibkr.password")

if ibUser is "" or ibPass is "" then
  return "missing_credentials"
end if

tell application "System Events"
  set procName to "JavaApplicationStub"
  repeat 90 times
    if exists process procName then
      exit repeat
    end if
    delay 1
  end repeat

  if not (exists process procName) then
    return "process_not_found"
  end if

  tell process procName
    set frontmost to true

    repeat 60 times
      if (count of windows) > 0 then
        exit repeat
      end if
      delay 1
    end repeat

    if (count of windows) = 0 then
      return "window_not_found"
    end if

    set targetWindow to window 1

    set windowPos to position of targetWindow
    set baseX to item 1 of windowPos
    set baseYPos to item 2 of windowPos

    click at {baseX + 295, baseYPos + 279}
    delay 0.2

    keystroke "a" using {command down}
    keystroke ibUser
    delay 0.2

    key code 48
    delay 0.2

    keystroke ibPass
    delay 0.2

    click at {baseX + 205, baseYPos + 380}
    delay 0.2

    key code 36
  end tell
end tell

return "submitted"
