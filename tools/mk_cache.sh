#!/bin/shell

filepath=$(cd "$(dirname "$0")"; pwd) 
echo working path: $filepath'/cache'

mkdir -p cache

for account in $filepath/accounts/*; do
    mkdir -p $account'/data'

    cache=$account'/data/cache'
    if ! test -e $cache; then
        echo $cache not exists, ready to link
        ln -s $filepath'/cache' $cache
    
    elif test -L $cache; then
        : #echo $cache is link, skip

    elif test -d $cache; then
        echo $cache is dir, remove and to link
        mv $cache/* $filepath/cache
        rm -rf $cache
        ln -s $filepath/cache $cache
    
    else
        echo $cache error!!!!
    fi
done

echo done

