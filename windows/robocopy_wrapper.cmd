c:\windows\system32\robocopy.exe %*
@echo off 

echo KOKOKOK %ERRORLEVEL%

IF %ERRORLEVEL% EQU 0 SET ERRORLEV=0
IF %ERRORLEVEL% EQU 1 SET ERRORLEV=0
IF %ERRORLEVEL% EQU 2 SET ERRORLEV=0
IF %ERRORLEVEL% EQU 4 SET ERRORLEV=0
IF %ERRORLEVEL% EQU 8 SET ERRORLEV=1
IF %ERRORLEVEL% EQU 16 SET ERRORLEV=1

echo YOYO %ERRORLEV%

IF %ERRORLEVEL% EQU -1 (
	SET ERRORLEV=1
	echo ""
	echo ""
	echo ROBOCOPY TERMINATED UNEXPECTEDLY WiTH EXIT CODE %ERRORLEVEL%
)

exit /B %ERRORLEV%

rem 0	No errors occurred and no files were copied.
rem 1	One of more files were copied successfully.
rem 2	Extra files or directories were detected.  Examine the log file for more information.
rem 4	Mismatched files or directories were detected.  Examine the log file for more information.
rem 8	Some files or directories could not be copied and the retry limit was exceeded.
rem 16	Robocopy did not copy any files.  Check the command line parameters and verify that Robocopy has enough rights to write to the destination folder.
rem -1  Robocopy been termintaed unexpectedly 