job "{{ sync_job_name }}" {
  datacenters = ["DC1"]

  type = "system"

  periodic {
    cron             = "{{ jobcron }}"
    prohibit_overlap = true
  }
  
  constraint {
    attribute = "${attr.kernel.name}"
    value     = "linux"
  }
  
  group "{{ sync_job_name }}" {
    count = 1

    task "sync" {
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
        command = ""
        args    = ["sync","-id","{{ xcpindexname }}"]
      }
    }
  }
}
