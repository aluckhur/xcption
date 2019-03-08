job "scan_job2_192.168.100.2-_xcp_src9" {
  datacenters = ["DC1"]

  type = "batch"

  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }
  
  group "scan_job2_192.168.100.2-_xcp_src9" {
    count = 1
    reschedule {
      attempts = 0
    }
    restart {
      attempts = 0
      mode     = "fail"
    }
    task "baseline" {
      driver = "raw_exec"
	  resources {
	    cpu    = 100
	    memory = 200
	  }
      logs {
        max_files     = 10
        max_file_size = 10
      }	  
      config {
        command = "/usr/sbin/xcp"
        args    = ["copy","-newid","scan-192.168.100.2-_xcp_src9-192.168.100.4-_xcp_dst9","192.168.100.2:/xcp/src9","192.168.100.4:/xcp/dst9"]
      }
    }
  }
}