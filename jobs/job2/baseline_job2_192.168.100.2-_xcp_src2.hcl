job "baseline_job2_192.168.100.2-_xcp_src2" {
  datacenters = ["DC1"]

  type = "batch"

  periodic {
    cron             = "0 0 31 2 *"
    prohibit_overlap = true
  }
  
  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }
  
  group "baseline_job2_192.168.100.2-_xcp_src2" {
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
	    memory = 800
	  }
      logs {
        max_files     = 10
        max_file_size = 10
      }	  
      config {
        command = "/usr/sbin/xcp"
        args    = ["copy","-newid","192.168.100.2-_xcp_src2-192.168.100.4-_xcp_dst2","192.168.100.2:/xcp/src2","192.168.100.4:/xcp/dst2"]
      }
    }
  }
}