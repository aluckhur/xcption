job "sync_job2_192.168.100.2-_xcp_src6" {
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
  
  group "sync_job2_192.168.100.2-_xcp_src6" {
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
        args    = ["sync","-id","192.168.100.2-_xcp_src6-192.168.100.4-_xcp_dst6"]
      }
    }
  }
}