job "baseline_job1_192.168.100.2-_xcp_src10" {
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
  
  group "baseline_job1_192.168.100.2-_xcp_src10" {
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
        command = "/usr/local/bin/xcp"
        args    = ["copy","-newid","192.168.100.2-_xcp_src10-192.168.100.3-_xcp_dst10","192.168.100.2:/xcp/src10","192.168.100.3:/xcp/dst10"]
      }
    }
  }
}