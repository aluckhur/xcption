job "xcption_gc_system" {
  datacenters = ["DC1"]

  type = "system"

  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }

  constraint {
      operator = "distinct_hosts"
      value = "true"
  }
  
  group "xcption_gc_system" {
    restart {
      delay    = "30s"
    }

    task "xcption_gc_system" {
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
          command = "/root/xcption/system/xcption_gc_system.sh"
      }
    }
  }
}