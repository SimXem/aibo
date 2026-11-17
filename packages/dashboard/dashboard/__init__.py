"""The dashboard kit: what every dashboard's site is made of, and nothing about forecasts.

A dashboard turns its own runs into blobs (the JSON its page reads) and tables
(the rows of its download); the kit does the rest:

    page.py      the page from its chunks, with the blobs spliced in; reading the
                 data back out of a published page
    download.py  CSV text and the zip behind the page's download button
    site.py      the site folder: writing it, checking it is complete, hashing
                 what it publishes

Stdlib only: building a dashboard never needs a key or an install.
"""
__version__ = "0.1.0"
