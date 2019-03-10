job "rescan_job2_192.168.100.2-_xcp_src7" {
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
  
  group "rescan_job2_192.168.100.2-_xcp_src7" {
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
        command = "/usr/local/bin/xcp"
        args    = ["sync","-id","scan-192.168.100.2-_xcp_src7-192.168.100.4-_xcp_dst7"]
      }
    }
  }
}