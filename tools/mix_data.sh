#!/bin/shell

working_path=$(cd "$(dirname "$0")""/.."; pwd) 
echo working path: $working_path

link_cache() {
    mixed=$working_path'/mixed_data/'$1
    mkdir -p $mixed

    for account in $working_path/accounts/*; do
        target=$account'/data/'$1
        mkdir -p "$(dirname "$target")"

        if ! test -e $target; then
            echo $target not exists, ready to link
            ln -s $mixed $target
        
        elif test -L $target; then
            : #echo $target is link, skip

        elif test -d $target; then
            echo $target is dir, remove and to link
            mv $target/* $mixed
            rm -rf $target
            ln -s $mixed $target
        
        else
            echo $target error!!!!
        fi
    done
}

link_cache cache
link_cache images
link_cache videos
link_cache voices

echo done

