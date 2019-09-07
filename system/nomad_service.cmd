mkdir c:\NetApp\XCP\log
del /Q c:\NetApp\XCP\log\NomadLog.txt
c:\NetApp\XCP\nomad.exe agent -config=c:\NetApp\XCP\client.hcl > c:\NetApp\XCP\log\NomadLog.txt
