#!/bin/shell

working_path=$(cd "$(dirname "$0")""/.."; pwd) 
echo working path: $working_path

usage() {
    echo "Usage: sh tools/backup.sh [options]"
    echo "Options:"
    echo "  -h           Show this help message and exit"
    echo "  -a           Backup full data"
    echo "  -i           Backup import data in mongodb"
    echo "  -s           Backup session.token and device.json"
    exit 1
}


if [ $# -eq 0 ]; then
    usage
fi

output="backups/"`date "+%Y_%m_%d_%H_%M_%S"`

backup_full_mongodb() {
    mongodump -o $output/mongodb
    echo "Backup full mongodb data to $output/mongodb"
}

backup_import_data_in_mongodb() {
    mongodump -d PallasBot -c blacklist -o $output/mongodb
    mongodump -d PallasBot -c config -o $output/mongodb
    mongodump -d PallasBot -c group_config -o $output/mongodb
    mongodump -d PallasBot -c user_config -o $output/mongodb
    mongodump -d PallasBot -c context -o $output/mongodb

    mongodump -d gocq-database -c image-cache -o $output/mongodb
    mongodump -d gocq-database -c video-cache -o $output/mongodb

    echo "Backup import data in mongodb to $output/mongodb"
}

backup_session() {
    for path in `find $working_path/accounts -name "device.json" -or -name "session.token"`; do
        account=`basename $(dirname $path)`
        target=$output/accounts/$account
        mkdir -p $target
        cp $path $target
    done
    
    echo "Backup session.token and device.json to $output/accounts"
}

while getopts "ahis" arg; do
    case $arg in
        a)
            backup_full_mongodb
            backup_session
            ;;
        i)
            backup_import_data_in_mongodb
            ;;
        s)
            backup_session
            ;;
        h)
            usage
            ;;
        ?)
            usage
            ;;
    esac
done