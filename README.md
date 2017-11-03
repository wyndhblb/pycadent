# PyCadent

A plugin for using graphite and graphite-api with the the `cadent` backend

This is based on https://github.com/brutasse/graphite-cyanite.git


# Installation
    
    pip install git+https://github.com/wyndhblb/pycadent
 

# Using with graphite-api

In your graphite-api config file::

    cadent:
        urls:
            - http://cadent-host:port/rootpath
    finders:
        - cadent.CadentFinder

# Using with graphite-web

In your graphite's `local_settings.py`

    STORAGE_FINDERS = (
        'cadent.CadentFinder',
    )

    CADENT_URLS = (
        'http://host:port/rootpath',
    )

Where `host:port` is the location of the Cadent HTTP API. If you run
Cadent on multiple hosts, specify all of them to load-balance traffic

    # Graphite-API
    cadent:
        urls:
            - http://host1:port
            - http://host2:port

    # Graphite-web
    CADENT_URLS = (
        'http://host1:port',
        'http://host2:port',
    )


