mkdir c:\Nomad\log
del /Q c:\Nomad\log\*
C:\Nomad\nomad.exe agent -config=c:\nomad\client.hcl > c:\nomad\log\nomadlog.txt