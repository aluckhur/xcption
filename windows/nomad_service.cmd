mkdir c:\NetApp\XCP\log
del /Q c:\NetApp\XCP\log\NomadLog.txt
rmdir /Q /S C:\NetApp\XCP\lib\alloc
c:\NetApp\XCP\nomad.exe agent -config=c:\NetApp\XCP\client.hcl > c:\NetApp\XCP\log\NomadLog.txt
