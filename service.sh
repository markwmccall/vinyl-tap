#!/bin/bash
# Manage the vinyl-web service
# Usage: ./service.sh [start|stop|restart|status|logs]

case "${1:-status}" in
    start)
        sudo systemctl start vinyl-web
        echo "Started."
        ;;
    stop)
        sudo systemctl stop vinyl-web
        echo "Stopped."
        ;;
    restart)
        sudo systemctl restart vinyl-web
        echo "Restarted."
        ;;
    status)
        sudo systemctl status vinyl-web
        ;;
    logs)
        lines="${2:-50}"
        sudo journalctl -u vinyl-web -n "$lines" -f
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status|logs]"
        exit 1
        ;;
esac
