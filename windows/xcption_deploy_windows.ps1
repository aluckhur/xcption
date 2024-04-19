
param (
   [string]$XCPtionServer = $(throw "-XCPtionServer is required."), 
   [string]$XCPtionServiceUser = $(throw "-XCPtionServiceUser is required."),
   [string]$XCPtionServicePwd
)

if (-not $XCPtionServicePwd) {
	$pwd = Read-Host -AsSecureString "XCPtion Service Passwd"
	$XCPtionServicePwd = (New-Object PSCredential "user",$pwd).GetNetworkCredential().Password
}


$InstallDir = "C:\NetApp\XCP\"
$LogDir = $InstallDir+"Log\"
$XCPtionServiceName = "XCPtionNomad"


function Unzip
{
    Param([string]$zipfile, [string]$outpath)

    Write-Host "Extracting file: $zipfile to directory: $outpath"
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipfile, $outpath) 
}


Add-Type -AssemblyName System.IO.Compression.FileSystem
if (-not ([System.Management.Automation.PSTypeName]'ServerCertificateValidationCallback').Type)
{
$certCallback = @"
    using System;
    using System.Net;
    using System.Net.Security;
    using System.Security.Cryptography.X509Certificates;
    public class ServerCertificateValidationCallback
    {
        public static void Ignore()
        {
            if(ServicePointManager.ServerCertificateValidationCallback ==null)
            {
                ServicePointManager.ServerCertificateValidationCallback += 
                    delegate
                    (
                        Object obj, 
                        X509Certificate certificate, 
                        X509Chain chain, 
                        SslPolicyErrors errors
                    )
                    {
                        return true;
                    };
            }
        }
    }
"@
    Add-Type $certCallback
 }
[ServerCertificateValidationCallback]::Ignore()


if (-not (Test-Path $InstallDir -Type Container)) {
	Write-Host "Creating installation directory:$InstallDir"
	New-Item -ItemType Directory -Path $InstallDir
}

if (-not (Test-Path $LogDir -Type Container)) {
	New-Item -ItemType Directory -Path $LogDir
}


# Write-Host "Getting required Microsoft Visual C++ Redistributable Update (Required for XCP)"
# GetFile  -URL https://aka.ms/vs/16/release/vc_redist.x64.exe -DestinationFile vc_redist.x64.exe
# Write-Host "Installing Microsoft Visual C++ Redistributable Update"
# & $($TempDir+"vc_redist.x64.exe") "/q" "/log" $($LogDir+"vcredist_x64.log") "/norestarts"


# Write-Host "Getting SCP client for windows to copy required files from XCP server"
# GetFile  -URL https://the.earth.li/~sgtatham/putty/latest/w64/pscp.exe -DestinationFile pscp.exe
 
if (-not (Test-Path $($InstallDir+'xcp.exe') -Type Leaf)) {
	Write-Host "Fetching xcp.exe from XCPtion server"
	Unzip $($TempDir+"xcp_windows.zip") $InstallDir
}
if (-not (Test-Path $($InstallDir+'nomad.exe') -Type Leaf)) {
	Write-Host "Fetching nomad.exe from XCPtion server"
	Unzip $($TempDir+"nomad_windows.zip") $InstallDir
}
$NomadClientHCLFile = $InstallDir+'client.hcl'
Write-Host "Creating nomad client configuration file:$NomadClientHCLFile"

Set-Content -Value "bind_addr    = ""0.0.0.0""" -Path $NomadClientHCLFile
Add-Content -Value "region       = ""DC1""" -Path $NomadClientHCLFile 
Add-Content -Value "datacenter   = ""DC1""" -Path $NomadClientHCLFile 
Add-Content -Value "data_dir     = ""$(($InstallDir -Replace "\\","/")+'lib')""" -Path $NomadClientHCLFile 
Add-Content -Value "log_file     = ""$(($LogDir -Replace "\\","/")+'NomadLog.txt')""" -Path $NomadClientHCLFile 
#Add-Content -Value "log_level   = ""DEBUG""" -Path $NomadClientHCLFile 
Add-Content -Value "leave_on_interrupt = true" -Path $NomadClientHCLFile 
Add-Content -Value "leave_on_terminate = true" -Path $NomadClientHCLFile 
Add-Content -Value "client {" -Path $NomadClientHCLFile 
Add-Content -Value "  enabled       = true" -Path $NomadClientHCLFile 
Add-Content -Value "  network_speed = 10" -Path $NomadClientHCLFile 
Add-Content -Value "  servers = [""$($XCPtionServer)""]" -Path $NomadClientHCLFile 
Add-Content -Value "  gc_inode_usage_threshold = 90" -Path $NomadClientHCLFile 
Add-Content -Value "  gc_disk_usage_threshold = 90" -Path $NomadClientHCLFile 
Add-Content -Value "  options { "-Path $NomadClientHCLFile 
Add-Content -Value "    ""driver.raw_exec.enable"" = ""1""" -Path $NomadClientHCLFile 
Add-Content -Value "  }" -Path $NomadClientHCLFile 
Add-Content -Value "}" -Path $NomadClientHCLFile 
Add-Content -Value "advertise {" -Path $NomadClientHCLFile 
Add-Content -Value "  http = ""$($env:computername):4646""" -Path $NomadClientHCLFile 
Add-Content -Value "  rpc  = ""$($env:computername):4647""" -Path $NomadClientHCLFile 
Add-Content -Value "  serf = ""$($env:computername):4648""" -Path $NomadClientHCLFile 
Add-Content -Value "}" -Path $NomadClientHCLFile 


if (Get-Service $XCPtionServiceName -ErrorAction SilentlyContinue)
{
    Write-Host "Service:$XCPtionServiceName already exists, removing it"
	Stop-Service -Name $XCPtionServiceName -OutVariable out
	$serviceToRemove = Get-WmiObject -Class Win32_Service -Filter "name='$XCPtionServiceName'"
    $out = $serviceToRemove.delete()
}

#remove previous nomad lib dir
if (Test-Path $($InstallDir+'lib\alloc') -Type Container) {
	Write-Host "Removing previous allocs"
	Remove-Item -LiteralPath $InstallDir'lib\alloc' -Force -Recurse
}


$binaryPath = $InstallDir+'nomad.exe'
Write-Host "Creating service:$XCPtionServiceName"
& sc.exe create "$XCPtionServiceName" binPath= "$binaryPath agent -config=$NomadClientHCLFile" Start= auto DisplayName= "$XCPtionServiceName"
& sc.exe config "$XCPtionServiceName" obj= "$XCPtionServiceUser" password= "$XCPtionServicePWD"

Write-Host "Starting service:$XCPtionServiceName"
Start-Service -Name $XCPtionServiceName
Write-Host "Installation completed"


