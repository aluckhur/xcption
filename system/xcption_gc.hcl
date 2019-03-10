job "xcption_gc" {
  datacenters = ["DC1"]

  type = "batch"

  periodic {
    cron             = "* * * * *"
    prohibit_overlap = true
  }
  
  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }

  constraint {
      operator = "distinct_hosts"
      value = "true"
  }
  
  group "xcption_gc" {
    count = 3

    reschedule {
      attempts  = 0
    }
    restart {
      attempts = 0
      mode     = "fail"
    }   

    task "xcption_gc" {
      driver = "raw_exec"
    

  	  resources {
  	    cpu    = 100
  	    memory = 20
  	  }
        logs {
          max_files     = 10
          max_file_size = 10
        }	  
        config {
          command = "/root/xcption/system/xcption_gc.sh"
        }
      }
  }
}
