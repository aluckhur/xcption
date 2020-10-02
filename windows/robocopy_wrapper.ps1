$RobocopyErrorCodes = @{}
$RobocopyErrorCodes[0] = "No errors occurred and no files were copied."
$RobocopyErrorCodes[1] = "One of more files were copied successfully."
$RobocopyErrorCodes[2] = "Extra files or directories were detected.  Examine the log file for more information"
$RobocopyErrorCodes[4] = "Mismatched files or directories were detected.  Examine the log file for more information."
$RobocopyErrorCodes[8] = "Some files or directories could not be copied and the retry limit was exceeded"
$RobocopyErrorCodes[16] = "Robocopy did not copy any files.  Check the command line parameters and verify that Robocopy has enough rights to write to the destination folder"
$RobocopyErrorCodes[-1] = "Robocopy been termintaed unexpectedly"

$i = 0
$arguments = ''

#XD will be used for exclude diretories 
$XD = $False 
foreach ($a in $args) {
    #args[0] is the src #args[1] is the dest and XD true  
    if ($i -eq 0 -or $i -eq 1 -or $XD -eq $True) {
        $arguments += '"'+$a+'" '
    } else {
        $arguments += $a+' '
    }
    if ($a -eq "/XD") {
        $XD = $True
    }
    $i++
    
}

Write-host $arguments

$oInfo = New-Object System.Diagnostics.ProcessStartInfo
$oInfo.FileName  = "robocopy"
$oInfo.Arguments = $arguments
$oInfo.UseShellExecute = $False
$oInfo.RedirectStandardOutput = $True

$oProcess = New-Object System.Diagnostics.Process
$oProcess.StartInfo = $oInfo

[Void]$oProcess.Start()

$bDone = $False

$StartTime = Get-Date

$scanned = 0
$modified = 0
$new = 0
$filegone = 0
$dirgone = 0
$errors = 0
$same = 0

$newbytes = 0

#will be set to true if the unique string to robocopy successful end will be found in the output, if not the exit code will be failure 
$endstring = $False

while (!$bDone)
{

    $lines = @()
    
    $nowlines = $oProcess.StandardOutput.ReadLine()
    if ($nowlines) {
        $lines += $nowlines.Split([Environment]::NewLine)
    }

    $processexited = $oProcess.HasExited

    if ($processexited) {
         $endlines = $oProcess.StandardOutput.ReadToEnd()
         if ($endlines) {
            $lines += $endlines.Split([Environment]::NewLine)
        }
        $bDone = $True
    } 

    $SpanTime = New-TimeSpan -Start $StartTime -End (Get-Date)
    $seconds = $SpanTime.Seconds
    $minutes = $SpanTime.Minutes
    $hours   = $SpanTime.Hours

    $logtick = [math]::truncate($SpanTime.TotalSeconds / 10)

    ForEach ($line in $lines) {

        $line = $line -replace "`0", ""
        
        if ($line) {
            if ($line -match '\s+Modified\s+(\d+)') {
                $modified += 1
                $newbytes += $matches[1]
            } elseif ($line -match '\s+Newer\s+(\d+)') {
                $modified += 1
                $newbytes += $matches[1]
            } elseif ($line -match '\s+Older\s+(\d+)') {
                $modified += 1
                $newbytes += $matches[1]                                                   
            } elseif ($line -match '\s+New File\s+(\d+)') {
                $new += [regex]::Matches($line, "\sNew File\s+\d+").count  
                $newbytes += $matches[1]
            } elseif ($line -match '\s+New Dir\s+(\d+)') {
                $new += 1 
            } elseif ($line -match '\ssame\s+\d+') {                
                $same += [regex]::Matches($line, "\ssame\s+\d+").count          
            } elseif ($line -match '\s+tweaked\s+(\d+)') {
                $modified += 1         
            } elseif ($line -match '^\s*\*EXTRA File\s+(\d+)') {
                $filegone += 1 
            } elseif ($line -match '^\s*\*EXTRA Dir\s+-?(\d+)') {
                $dirgone += 1 
            } elseif ($line -match '^\s+(\d+)\s+\\.+\\\s*$') {
                $dir += 1 
            } elseif ($line -match 'ERROR \d+ \(') {
                Write-Output $line 
                $errors += 1
            #removed as part of removal of /V robocopy option due to problematic logging when robocopy works in MP mode 
            #} elseif ($line -match '^\s*\\\\') {
            #    #skip split lines         
            #} elseif ($line -match '^\s*(\d+)%\s*$') {
            #    #skip lines 
            #} elseif ($line -match '^\s*$') {
            #    #skip empty lines         
            } else {
                Write-Host "$($line)"
            }

            if ($line -match "Dirs \:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)") {
                $errors = [int]$matches[5]
                $scanned = [int]$matches[1]
                $new = [int]$matches[2]
            }
            
            if ($line -match "Files \:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)") {
                $errors += [int]$matches[5]
                $scanned += [int]$matches[1]
                $new += [int]$matches[2]
            }
            
            if ($line -match "Bytes \:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)") {
                $newbytes += [int64]$matches[2]
            }
            
            if ($line -match "Ended \:") {
                $endstring = $True 
            }           
        }
    }
    
    if ($logtick -ne $oldlogtick -or $processexited) {
        $oldlogtick = $logtick

        $time = [string]$hours+'h'+[string]$minutes+'m'+[string]$seconds+'s'      

        if ($seconds -eq 0 ) {$seconds = 1}
        $bw = [math]::Round($newbytes/1024/1024,2)
        $bwqunatifier = "MiB"
        
        $bws = [math]::Round($bw/($hours*3600+$minutes*60+$seconds),2)
        $bwsquantifier = "MiB/s"

        if ($bw -ge 1000 -and $bw -lt 1000000) {
            $bw = [math]::Round($bw/1024,2)
            $bwqunatifier = "GiB" 
        } elseif ($bw -ge 1000000) {
            $bw = [math]::Round($bw/1024/1024,2)
            $bwqunatifier = "TiB" 
        }

        if ($bws -ge 1000 -and $bws -lt 1000000) {
            $bws = [math]::Round($bws/1024,2)
            $bwsqunatifier = "GiB/s" 
        } elseif ($bws -ge 1000000) {
            $bws = [math]::Round($bws/1024/1024,2)
            $bwsqunatifier = "TiB" 
        }        

        if (-not $processexited) {
            $scanned = $modified + $new + $same   
        }

        #add new line before the final line 
        if ($processexited) {
            Write-Output ""
            Write-Output ""
        }
        
        Write-Host $('{0:N0}' -f ($scanned)) 'scanned,' $('{0:N0}' -f ($new)) 'copied,' $('{0:N0}' -f ($modified)) 'modification,' $('{0:N0}' -f ($errors)) 'error,' $('{0:N0}' -f ($filegone)) 'file.gone,' $('{0:N0}' -f ($dirgone)) 'dir.gone,' "$($bw)$($bwqunatifier) ($($bws)$($bwsquantifier))," $time
    }
    
    if ($bDone) {
        
        $exitcode = $oProcess.ExitCode 
        if ($exitcode -le 16 -and $exitcode -ge 0) {
            $exitmessage = $RobocopyErrorCodes[$exitcode]
            $exitcode = 0
        } else {                 
            $exitmessage = "robocopy ended with undocumented exitcode: $exitcode"
        }
       
        if ($exitcode -lt -1 -or $exitcode -gt 16) {
            $exitmessage = "robocopy ended with undocumented exitcode: $exitcode"
            $exitcode = 1
        }
    }    
}

if (-not $endstring) {
    $exitmessage = 'could not identify the robocopy summary indicating the job is completed'
    $exitcode = 1
}

Write-Output ""
Write-Output "Exit Code: $exitcode Exit Message: $exitmessage"
#this sleep is required to let nomad pull the log. in some case it been observered that nomad delete the log before the it pulled completly intp the nomad cache on the server 
Sleep 20

exit $exitcode
