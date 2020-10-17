
$url = $args[0]
$destpath = $args[1]

$a = wget $url -outfile $destpath -ErrorVariable e 

if (-not $e) {
	while ($True) {
		Write-Host "success downloading file from $url to $destpath"
		Sleep 10
	}
}

Exit 1


