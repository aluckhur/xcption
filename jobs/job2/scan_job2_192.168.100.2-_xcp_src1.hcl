job "scan_job2_192.168.100.2-_xcp_src1" {
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
  
  group "scan_job2_192.168.100.2-_xcp_src1" {
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
        args    = ["copy","-newid","scan-192.168.100.2-_xcp_src1-192.168.100.4-_xcp_dst1","192.168.100.2:/xcp/src1","192.168.100.4:/xcp/dst1"]
      }
    }
  }
}