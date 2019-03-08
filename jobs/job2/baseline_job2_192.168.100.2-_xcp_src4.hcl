job "baseline_job2_192.168.100.2-_xcp_src4" {
  datacenters = ["DC1"]

  type = "batch"

  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }
  
  group "baseline_job2_192.168.100.2-_xcp_src4" {
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
        args    = ["copy","-newid","192.168.100.2-_xcp_src4-192.168.100.4-_xcp_dst4","192.168.100.2:/xcp/src4","192.168.100.4:/xcp/dst4"]
      }
    }
  }
}