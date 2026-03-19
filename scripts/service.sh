#!/bin/bash
# Manage the vinyltap service
# Usage: ./service.sh [start|stop|restart|status|logs]

case "${1:-status}" in
    start)
        sudo systemctl start vinyltap
        echo "Started."
        ;;
    stop)
        sudo systemctl stop vinyltap
        echo "Stopped."
        ;;
    restart)
        sudo systemctl restart vinyltap
        echo "Restarted."
        ;;
    status)
        sudo systemctl status vinyltap
        ;;
    logs)
        lines="${2:-50}"
        sudo journalctl -u vinyltap -n "$lines" -f
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status|logs]"
        exit 1
        ;;
esac
