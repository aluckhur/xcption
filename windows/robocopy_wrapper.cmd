
c:\windows\system32\robocopy.exe %*
@echo off 
IF ERRORLEVEL 0 SET ERRORLEV=0
IF ERRORLEVEL 1 SET ERRORLEV=0
IF ERRORLEVEL 2 SET ERRORLEV=0
IF ERRORLEVEL 4 SET ERRORLEV=0
IF ERRORLEVEL 8 SET ERRORLEV=1
IF ERRORLEVEL 16 SET ERRORLEV=1

exit /B ERRORLEV=%ERRORLEV%

rem 0	No errors occurred and no files were copied.
rem 1	One of more files were copied successfully.
rem 2	Extra files or directories were detected.  Examine the log file for more information.
rem 4	Mismatched files or directories were detected.  Examine the log file for more information.
rem 8	Some files or directories could not be copied and the retry limit was exceeded.
rem 16	Robocopy did not copy any files.  Check the command line parameters and verify that Robocopy has enough rights to write to the destination folder.