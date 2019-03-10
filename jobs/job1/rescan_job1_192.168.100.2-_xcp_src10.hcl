job "rescan_job1_192.168.100.2-_xcp_src10" {
  datacenters = ["DC1"]

  type = "batch"

  periodic {
    cron             = "*/1 * * * *"
    prohibit_overlap = true
  }
  
  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }
  
  group "rescan_job1_192.168.100.2-_xcp_src10" {
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
	    memory = 800
	  }
      logs {
        max_files     = 10
        max_file_size = 10
      }	  
      config {
        command = "/usr/sbin/xcp"
        args    = ["sync","-id","scan-192.168.100.2-_xcp_src10-192.168.100.3-_xcp_dst10"]
      }
    }
  }
}