job "rescan_job2_192.168.100.2-_xcp_src3" {
  datacenters = ["DC1"]

  type = "batch"

  periodic {
    cron             = "*/15 * * * *"
    prohibit_overlap = true
  }
  
  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }
  
  group "rescan_job2_192.168.100.2-_xcp_src3" {
    count = 1
    reschedule {
      attempts  = 0
    }
    restart {
      attempts = 0
      mode     = "fail"
    }
    task "sync" {
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
        args    = ["sync","-id","scan-192.168.100.2-_xcp_src3-192.168.100.4-_xcp_dst3"]
      }
    }
  }
}