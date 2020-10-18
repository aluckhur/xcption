
$url = $args[0]
$destpath = $args[1]

$a = wget $url -outfile $destpath -ErrorVariable e 

if (-not $e) {
	Write-Host  "success file download from $args[0] to $args[1] on $($env:computername)"
	Exit 0
}

Write-Host  "failed file download from $args[0] to $args[1] on $($env:computername)"
Exit 1


