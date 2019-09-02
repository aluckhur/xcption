

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest  https://aka.ms/vs/16/release/vc_redist.x64.exe -OutFile vc_redist.x64.exe
Invoke-WebRequest  https://the.earth.li/~sgtatham/putty/latest/w64/pscp.exe -OutFile pscp.exe
.\pscp.exe -pw Netapp1! root@192.168.0.61:/root/xcption/system/nomad_windows.zip nomad_windows.zip
.\pscp.exe -pw Netapp1! root@192.168.0.61:/root/xcption/system/xcp_windows.zip xcp_windows.zip 
.\pscp.exe -pw Netapp1! root@192.168.0.61:/root/xcption/system/license license 
.\pscp.exe -pw Netapp1! root@192.168.0.61:/root/xcption/system/nomad_service.cmd nomad_service.cmd
.\pscp.exe -pw Netapp1! root@192.168.0.61:/root/xcption/system/robocopy_wrapper.cmd robocopy_wrapper.cmd 