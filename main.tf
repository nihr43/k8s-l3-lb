resource "kubernetes_daemonset" "l3lb" {
  metadata {
    name      = "l3lb"
    namespace = "default"

    labels = {
      k8s-app = "l3lb"
    }
  }

  spec {
    selector {
      match_labels = {
        name = "l3lb"
      }
    }

    template {
      metadata {
        labels = {
          name = "l3lb"
        }
      }

      spec {
        host_network                    = true
        automount_service_account_token = true

        container {
          name  = "l3lb"
          image = "images.local:30500/l3lb"

          env {
            name  = "L3LB_PREFIX"
            value = "10.0.100.0/24"
          }

          env {
            name  = "L3LB_INTERFACE"
            value = "lo"
          }

          security_context {
            capabilities {
              add = ["NET_ADMIN"]
            }
          }
        }
      }
    }
  }
}
