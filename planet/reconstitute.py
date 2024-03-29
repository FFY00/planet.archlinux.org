"""
Reconstitute an entry document from the output of the Universal Feed Parser.

The main entry point is called 'reconstitute'.  Input parameters are:

  results: this is the entire hash table return by the UFP
  entry:   this is the entry in the hash that you want reconstituted

The value returned is an XML DOM.  Every effort is made to convert
everything to unicode, and text fields into either plain text or
well formed XHTML.

Todo:
  * extension elements
"""
import re, time, sgmllib
from xml.sax.saxutils import escape
from xml.dom import minidom, Node
from html5lib import html5parser
from html5lib.treebuilders import dom
import planet, config

try:
  from hashlib import md5
except:
  from md5 import new as md5

illegal_xml_chars = re.compile("[\x01-\x08\x0B\x0C\x0E-\x1F]", re.UNICODE)

def createTextElement(parent, name, value):
    """ utility function to create a child element with the specified text"""
    if not value: return
    if isinstance(value,str):
        try:
            value=value.decode('utf-8')
        except:
            value=value.decode('iso-8859-1')
    value = illegal_xml_chars.sub(invalidate, value)
    xdoc = parent.ownerDocument
    xelement = xdoc.createElement(name)
    xelement.appendChild(xdoc.createTextNode(value))
    parent.appendChild(xelement)
    return xelement

def invalidate(c): 
    """ replace invalid characters """
    return '<abbr title="U+%s">\ufffd</abbr>' % \
        ('000' + hex(ord(c.group(0)))[2:])[-4:]

def ncr2c(value):
    """ convert numeric character references to characters """
    value=value.group(1)
    if value.startswith('x'):
        value=chr(int(value[1:],16))
    else:
        value=chr(int(value))
    return value

nonalpha=re.compile('\W+',re.UNICODE)
def cssid(name):
    """ generate a css id from a name """
    try:
        name = nonalpha.sub('-',name.decode('utf-8')).lower().encode('utf-8')
    except:
        name = nonalpha.sub('-',name).lower()
    return name.strip('-')

def id(xentry, entry):
    """ copy or compute an id for the entry """

    if "id" in entry and entry.id:
        entry_id = entry.id
        if hasattr(entry_id, 'values'): entry_id = list(entry_id.values())[0]
    elif "link" in entry and entry.link:
        entry_id = entry.link
    elif "title" in entry and entry.title:
        entry_id = (entry.title_detail.base + "/" +
            md5(entry.title).hexdigest())
    elif "summary" in entry and entry.summary:
        entry_id = (entry.summary_detail.base + "/" +
            md5(entry.summary).hexdigest())
    elif "content" in entry and entry.content:

        entry_id = (entry.content[0].base + "/" + 
            md5(entry.content[0].value).hexdigest())
    else:
        return

    if xentry: createTextElement(xentry, 'id', entry_id)
    return entry_id

def links(xentry, entry):
    """ copy links to the entry """
    if 'links' not in entry:
       entry['links'] = []
       if 'link' in entry:
         entry['links'].append({'rel':'alternate', 'href':entry.link}) 
    xdoc = xentry.ownerDocument
    for link in entry['links']:
        if not 'href' in list(link.keys()): continue
        xlink = xdoc.createElement('link')
        xlink.setAttribute('href', link.get('href'))
        if 'type' in link:
            xlink.setAttribute('type', link.get('type'))
        if 'rel' in link:
            xlink.setAttribute('rel', link.get('rel',None))
        if 'title' in link:
            xlink.setAttribute('title', link.get('title'))
        if 'length' in link:
            xlink.setAttribute('length', link.get('length'))
        xentry.appendChild(xlink)

def date(xentry, name, parsed):
    """ insert a date-formated element into the entry """
    if not parsed: return
    formatted = time.strftime("%Y-%m-%dT%H:%M:%SZ", parsed)
    xdate = createTextElement(xentry, name, formatted)
    formatted = time.strftime(config.date_format(), parsed)
    xdate.setAttribute('planet:format', formatted.decode('utf-8'))

def category(xentry, tag):
    xtag = xentry.ownerDocument.createElement('category')
    if 'term' not in tag or not tag.term: return
    xtag.setAttribute('term', tag.get('term'))
    if 'scheme' in tag and tag.scheme:
        xtag.setAttribute('scheme', tag.get('scheme'))
    if 'label' in tag and tag.label:
        xtag.setAttribute('label', tag.get('label'))
    xentry.appendChild(xtag)

def author(xentry, name, detail):
    """ insert an author-like element into the entry """
    if not detail: return
    xdoc = xentry.ownerDocument
    xauthor = xdoc.createElement(name)

    if detail.get('name', None):
        createTextElement(xauthor, 'name', detail.get('name'))
    else:
        xauthor.appendChild(xdoc.createElement('name'))

    createTextElement(xauthor, 'email', detail.get('email', None))
    createTextElement(xauthor, 'uri', detail.get('href', None))
        
    xentry.appendChild(xauthor)

def content(xentry, name, detail, bozo):
    """ insert a content-like element into the entry """
    if not detail or not detail.value: return

    data = None
    xdiv = '<div xmlns="http://www.w3.org/1999/xhtml">%s</div>'
    xdoc = xentry.ownerDocument
    xcontent = xdoc.createElement(name)

    if isinstance(detail.value,str):
        detail.value=detail.value.encode('utf-8')

    if 'type' not in detail or detail.type.lower().find('html')<0:
        detail['value'] = escape(detail.value)
        detail['type'] = 'text/html'

    if detail.type.find('xhtml')>=0 and not bozo:
        try:
            data = minidom.parseString(xdiv % detail.value).documentElement
            xcontent.setAttribute('type', 'xhtml')
        except:
            bozo=1

    if detail.type.find('xhtml')<0 or bozo:
        parser = html5parser.HTMLParser(tree=dom.TreeBuilder)
        html = parser.parse(xdiv % detail.value, encoding="utf-8")
        for body in html.documentElement.childNodes:
            if body.nodeType != Node.ELEMENT_NODE: continue
            if body.nodeName != 'body': continue
            for div in body.childNodes:
                if div.nodeType != Node.ELEMENT_NODE: continue
                if div.nodeName != 'div': continue
                try:
                    div.normalize()
                    if len(div.childNodes) == 1 and \
                        div.firstChild.nodeType == Node.TEXT_NODE:
                        data = div.firstChild
                        if illegal_xml_chars.search(data.data):
                            data = xdoc.createTextNode(
                                illegal_xml_chars.sub(invalidate, data.data))
                    else:
                        data = div
                        xcontent.setAttribute('type', 'xhtml')
                    break
                except:
                    # in extremely nested cases, the Python runtime decides
                    # that normalize() must be in an infinite loop; mark
                    # the content as escaped html and proceed on...
                    xcontent.setAttribute('type', 'html')
                    data = xdoc.createTextNode(detail.value.decode('utf-8'))

    if data: xcontent.appendChild(data)

    if detail.get("language"):
        xcontent.setAttribute('xml:lang', detail.language)

    xentry.appendChild(xcontent)

def location(xentry, long, lat):
    """ insert geo location into the entry """
    if not lat or not int: return

    xlat = createTextElement(xentry, '%s:%s' % ('geo','lat'), '%f' % lat)
    xlat.setAttribute('xmlns:%s' % 'geo', 'http://www.w3.org/2003/01/geo/wgs84_pos#')
    xlong = createTextElement(xentry, '%s:%s' % ('geo','long'), '%f' % int)
    xlong.setAttribute('xmlns:%s' % 'geo', 'http://www.w3.org/2003/01/geo/wgs84_pos#')

    xentry.appendChild(xlat)
    xentry.appendChild(xlong)

def source(xsource, source, bozo, format):
    """ copy source information to the entry """
    xdoc = xsource.ownerDocument

    createTextElement(xsource, 'id', source.get('id', source.get('link',None)))
    createTextElement(xsource, 'icon', source.get('icon', None))
    createTextElement(xsource, 'logo', source.get('logo', None))

    if 'logo' not in source and 'image' in source:
        createTextElement(xsource, 'logo', source.image.get('href',None))

    for tag in source.get('tags',[]):
        category(xsource, tag)

    author(xsource, 'author', source.get('author_detail',{}))
    for contributor in source.get('contributors',[]):
        author(xsource, 'contributor', contributor)

    if 'links' not in source and 'href' in source: #rss
        source['links'] = [{ 'href': source.get('href') }]
        if 'title' in source: 
            source['links'][0]['title'] = source.get('title')
    links(xsource, source)

    content(xsource, 'rights', source.get('rights_detail',None), bozo)
    content(xsource, 'subtitle', source.get('subtitle_detail',None), bozo)
    content(xsource, 'title', source.get('title_detail',None), bozo)

    date(xsource, 'updated', source.get('updated_parsed',time.gmtime()))

    if format: source['planet_format'] = format
    if not bozo == None: source['planet_bozo'] = bozo and 'true' or 'false'

    # propagate planet inserted information
    if 'planet_name' in source and 'planet_css-id' not in source:
        source['planet_css-id'] = cssid(source['planet_name'])
    for key, value in list(source.items()):
        if key.startswith('planet_'):
            createTextElement(xsource, key.replace('_',':',1), value)

def reconstitute(feed, entry):
    """ create an entry document from a parsed feed """
    xdoc=minidom.parseString('<entry xmlns="http://www.w3.org/2005/Atom"/>\n')
    xentry=xdoc.documentElement
    xentry.setAttribute('xmlns:planet',planet.xmlns)

    if 'language' in entry:
        xentry.setAttribute('xml:lang', entry.language)
    elif 'language' in feed.feed:
        xentry.setAttribute('xml:lang', feed.feed.language)

    id(xentry, entry)
    links(xentry, entry)

    bozo = feed.bozo
    if 'title' not in entry or not entry.title:
        xentry.appendChild(xdoc.createElement('title'))

    content(xentry, 'title', entry.get('title_detail',None), bozo)
    content(xentry, 'summary', entry.get('summary_detail',None), bozo)
    content(xentry, 'content', entry.get('content',[None])[0], bozo)
    content(xentry, 'rights', entry.get('rights_detail',None), bozo)

    date(xentry, 'updated', entry_updated(feed.feed, entry, time.gmtime()))
    date(xentry, 'published', entry.get('published_parsed',None))

    if 'dc_date.taken' in entry:
        date_Taken = createTextElement(xentry, '%s:%s' % ('dc','date_Taken'), '%s' % entry.get('dc_date.taken', None))
        date_Taken.setAttribute('xmlns:%s' % 'dc', 'http://purl.org/dc/elements/1.1/')
        xentry.appendChild(date_Taken)

    for tag in entry.get('tags',[]):
        category(xentry, tag)

    # known, simple text extensions
    for ns,name in [('feedburner','origLink')]:
        if '%s_%s' % (ns,name.lower()) in entry and \
            ns in feed.namespaces:
            xoriglink = createTextElement(xentry, '%s:%s' % (ns,name),
                entry['%s_%s' % (ns,name.lower())])
            xoriglink.setAttribute('xmlns:%s' % ns, feed.namespaces[ns])

    # geo location
    if 'where' in entry and \
        'type' in entry.get('where',[]) and \
        'coordinates' in entry.get('where',[]):
        where = entry.get('where',[])
        type = where.get('type',None)
        coordinates = where.get('coordinates',None)
        if type == 'Point':
            location(xentry, coordinates[0], coordinates[1])
        elif type == 'Box' or type == 'LineString' or type == 'Polygon':
            location(xentry, coordinates[0][0], coordinates[0][1])
    if 'geo_lat' in entry and \
        'geo_long' in entry:
        location(xentry, (float)(entry.get('geo_long',None)), (float)(entry.get('geo_lat',None)))
    if 'georss_point' in entry:
        coordinates = re.split('[,\s]', entry.get('georss_point'))
        location(xentry, (float)(coordinates[1]), (float)(coordinates[0]))
    elif 'georss_line' in entry:
        coordinates = re.split('[,\s]', entry.get('georss_line'))
        location(xentry, (float)(coordinates[1]), (float)(coordinates[0]))
    elif 'georss_circle' in entry:
        coordinates = re.split('[,\s]', entry.get('georss_circle'))
        location(xentry, (float)(coordinates[1]), (float)(coordinates[0]))
    elif 'georss_box' in entry:
        coordinates = re.split('[,\s]', entry.get('georss_box'))
        location(xentry, ((float)(coordinates[1])+(float)(coordinates[3]))/2, ((float)(coordinates[0])+(float)(coordinates[2]))/2)
    elif 'georss_polygon' in entry:
        coordinates = re.split('[,\s]', entry.get('georss_polygon'))
        location(xentry, (float)(coordinates[1]), (float)(coordinates[0]))

    # author / contributor
    author_detail = entry.get('author_detail',{})
    if author_detail and 'name' not in author_detail and \
        'planet_name' in feed.feed:
        author_detail['name'] = feed.feed['planet_name']
    author(xentry, 'author', author_detail)
    for contributor in entry.get('contributors',[]):
        author(xentry, 'contributor', contributor)

    # merge in planet:* from feed (or simply use the feed if no source)
    src = entry.get('source')
    if src:
        for name,value in list(feed.feed.items()):
            if name.startswith('planet_'): src[name]=value
        if 'id' in feed.feed:
            src['planet_id'] = feed.feed.id
    else:
        src = feed.feed

    # source:author
    src_author = src.get('author_detail',{})
    if (not author_detail or 'name' not in author_detail) and \
       'name' not in src_author and  'planet_name' in feed.feed:
       if src_author: src_author = src_author.__class__(src_author.copy())
       src['author_detail'] = src_author
       src_author['name'] = feed.feed['planet_name']

    # source
    xsource = xdoc.createElement('source')
    source(xsource, src, bozo, feed.version)
    xentry.appendChild(xsource)

    return xdoc

def entry_updated(feed, entry, default = None):
    chks = ((entry, 'updated_parsed'),
            (entry, 'published_parsed'),
            (feed,  'updated_parsed'),)
    for node, field in chks:
        if field in node and node[field]:
            return node[field]
    return default
