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

    -- 等待登录表单完全渲染：窗口出现后再等几秒让 Java UI 加载完毕
    delay 5

    click at {baseX + 295, baseYPos + 279}
    delay 0.3

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

  -- 等待"我理解并接受"/ "I understand and accept" 弹窗并自动点击
  delay 5
  tell process procName
    repeat 30 times
      try
        -- 尝试查找并点击"I accept"/"I understand"按钮
        set allButtons to every button of every window
        repeat with w in windows
          repeat with btn in (every button of w)
            set btnName to name of btn
            if btnName contains "Accept" or btnName contains "accept" or btnName contains "I understand" or btnName contains "接受" or btnName contains "理解" or btnName contains "OK" or btnName contains "Continue" then
              click btn
              delay 1
            end if
          end repeat
        end repeat
      on error
        -- 忽略错误，继续尝试
      end try

      -- 备用：检查弹窗中的复选框并点击确认按钮
      try
        repeat with w in windows
          repeat with cb in (every checkbox of w)
            set cbName to name of cb
            if cbName contains "accept" or cbName contains "understand" or cbName contains "接受" or cbName contains "理解" then
              if value of cb is 0 then
                click cb
                delay 0.3
              end if
            end if
          end repeat
          -- 点击确认按钮
          repeat with btn in (every button of w)
            set btnName to name of btn
            if btnName contains "Login" or btnName contains "Log In" or btnName contains "Continue" or btnName contains "OK" or btnName contains "Submit" then
              click btn
              delay 1
            end if
          end repeat
        end repeat
      on error
        -- 忽略
      end try

      delay 2
      -- 如果端口已就绪说明弹窗已过
      try
        do shell script "python3 -c 'import socket; s=socket.socket(); s.settimeout(1); s.connect((\"127.0.0.1\",4002)); print(1)'"
        exit repeat
      on error
        -- 端口未就绪，继续等
      end try
    end repeat
  end tell
end tell

return "submitted"
