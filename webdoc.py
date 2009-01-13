#!/usr/bin/python
## file:        webdoc.py
## author:      Andrea Vedaldien
## description: Implementation of webdoc.

import xml.sax
import xml.sax.saxutils
import re
import os
import sys 
import random
import copy
import htmlentitydefs

from xml.sax.handler import ContentHandler
from xml.sax         import parse
from urlparse        import urlparse
from urlparse        import urlunparse

# Create a dictonary that maps unicode characters to HTML entities
mapUnicodeToHtmlEntity = { }
for k, v in htmlentitydefs.entitydefs.iteritems():
    if v == "&" or v == "<" or v == ">": continue
    mapUnicodeToHtmlEntity [v.decode('latin-1')] = "&" + k.decode('latin-1') + u";"

# This indexes the document nodes by ID
nodeIndex = { }

def getUniqueNodeID(id = None):
    """
    getUniqueNodeID() generates an unique ID for a document node.
    getUniqueNodeID(id) generates an unique ID adding a suffix to id.
    """
    if id is None: id = "id"
    uniqueId = id
    count = 0
    while 1:
        if uniqueId not in nodeIndex: break
        count += 1
        uniqueId = "%s-%d" % (id, count)
    return uniqueId

def dumpIndex():
    """
    Dump the node index, for debugging purposes.
    """
    for x in nodeIndex.itervalues():
      print x

def ensureDir(dirName):
    """
    Create the directory DIRNAME if it does not exsits.   
    """
    if os.path.isdir(dirName):
        pass
    elif os.path.isfile(dirName):
        raise OSError("cannot create the direcory '%s'"
                      "because there exists already "
                      "a file with that name" % newdir)
    else:
        head, tail = os.path.split(dirName)
        if head and not os.path.isdir(head):
            ensureDir(head)
        if tail:
            os.mkdir(dirName)

def calcRelURL(toURL, fromURL):
    """
    Calculates a relative URL.
    """
    fromURL  = urlparse(fromURL)
    toURL    = urlparse(toURL)
    if not fromURL.scheme == toURL.scheme: return toURL
    if not fromURL.netloc == toURL.netloc: return toURL

    fromPath = fromURL.path.split("/") 
    toPath   = toURL.path.split("/")
    for j in xrange(len(fromPath) - 1): fromPath[j] += u"/"
    for j in xrange(len(toPath)   - 1): toPath[j] += u"/"

    # abs path: ['/', 'dir1/', ..., 'dirN/', 'file'] 
    # rel path: ['dir1/', ..., 'dirN/', 'file'] 
    # path with no file: ['dir1/', ..., 'dirN/', '']

    # remove common part from paths
    i = 0
    while True:
        if i >= len(fromPath): break
        if i >= len(toPath): break
        if not fromPath[i] == toPath[i]: break
        i = i + 1

    # can remove the first chunks, and convert the others except the
    # last one
    for j in xrange(len(fromPath) - 1):
        if len(fromPath[j]) > 1: fromPath[j] = u"../"
        else:                    fromPath[j] = u""

    fromPath = fromPath[i:-1]
    toPath = toPath[i:]
    relPath = u"".join(fromPath) + "".join(toPath)
    
    return urlunparse(["", "", relPath, "", "", toURL.fragment])

def calcRelHref(href, baseNode = None):
    """
    Transforms HREF into an URL relative to BASENODE.  It also lookups
    website IDs and correctly cross-references to them.
    """
    hrefURL = urlparse(href)
    if hrefURL.scheme == "" and hrefURL.netloc == "" and \
            nodeIndex.has_key(hrefURL.path):
        node = nodeIndex[hrefURL.path]
        relPath = node.getRelativePublishURL(baseNode)
        hrefURL = ("",
                   "",
                   relPath,
                   hrefURL.query,
                   hrefURL.fragment,
                   None)
    return urlunparse(hrefURL)

# --------------------------------------------------------------------    
class DocParsingError(Exception):
# --------------------------------------------------------------------
    def __init__(self, URL, row, column, message):
        self.URL = URL
        self.rowNumber = row
        self.columnNumber = column
        self.message = message

    def __str__(self):
        return "%s:%d:%d:%s" % (self.URL, 
                                self.rowNumber, 
                                self.columnNumber, 
                                self.message)

# --------------------------------------------------------------------    
class DocNode:
# --------------------------------------------------------------------
    def __init__(self, attrs, URL, locator):
        self.parent = None
        self.children = []
        self.attrs = attrs
        self.sourceURL = None
        self.sourceRow = None
        self.sourceColumn = None
        if attrs.has_key('id'):
            self.id = attrs['id']
        else:
            self.id = getUniqueNodeID()            
        if URL:
            if not URL is self.getSourceURL():
                self.sourceURL = URL
        if locator:
            self.sourceRow = locator.getLineNumber()
            self.sourceColumn = locator.getColumnNumber()
        nodeIndex[self.id] = self

    def __str__(self):
        return "%s:%d:%d:%s" % (self.getSourceURL(),
                                self.getSourceRow(),
                                self.getSourceColumn(),
                                self.getID())

    def dump(self):
        """
        Recusively dump the tree, for debugging purposes.
        """
        depth = self.getDepth()
        print " " * depth, self
        for x in self.children: x.dump()


    def isA(self, classInfo):
        """
        Returns TRUE if the node is of class CLASSINFO.
        """
        return isinstance(self, classInfo)

    def getID(self):
        """
        Returns the node ID
        """
        return self.id

    def getParent(self):
        """
        Return the node parent.
        """
        return self.parent

    def getChildren(self):
        """
        Return the list of node children.
        """
        return self.children

    def getAttributes(self):
        """
        Return the dictionary of node attributes.
        """
        return self.attrs

    def getDepth(self):
        """
        Return the depth of the node in the tree.
        """
        if self.parent:
            return self.parent.getDepth() + 1
        else:
            return 0

    def adopt(self, orfan):
        """
        Adds ORFAN to the node children and make the node the parent
        of ORFAN. ORFAN can also be a sequence of orfans.
        """
        if isinstance(orfan, DocNode):
            self.children.append(orfan)
            orfan.parent = self
        else:
            map(self.adopt, orfan)

    def copy(self):
        """
        Makes a shallow copy of the node.
        """
        return copy.copy(self)

    def recursiveCopy(self):
        """
        Makes a recursive copy of the node.
        """
        x = self.copy()
        x.children = []
        for y in self.children:
            x.adopt(y.recursiveCopy())
        return x

    def findAncestors(self, nodeType = None):
        """
        Return the node ancestors of type NODETYPE. If NODETYPE is
        None, returns all ancestors.
        """
        if nodeType is None:
            nodeType = DocNode
        if self.parent:
            if self.parent.isA(nodeType):
                found = [self.parent]
            else:
                found = []
            found = found + self.parent.findAncestors(nodeType)
            return found
        return []

    def findChildren(self, nodeType = None):
        """
        Returns the node chldren of type NODTYPE. If NODETYPE is None,
        returns all children.
        """
        if nodeType is None:
            nodeType = DocNode
        return [x for x in self.children if x.isA(nodeType)]

    def getSourceURL(self):
        """
        Get the URL of the source code file where the node was
        instantiated.
        """
        if self.sourceURL: 
            return self.sourceURL
        elif self.parent:
            return self.parent.getSourceURL()
        else:
            return ""
        
    def getSourceColumn(self):
        """
        Gets the column of the source code file where the node was
        instantiated.
        """
        if not self.sourceColumn is None: 
            return self.sourceColumn 
        elif self.parent:
            return self.parent.getSourceColumn()
        else:
            return -1 

    def getSourceRow(self):
        """
        Gets the row (line) of the source code file where the node was
        instantiated.
        """
        if not self.sourceRow is None: 
            return self.sourceRow 
        elif self.parent:
            return self.parent.getSourceRow()
        else:
            return -1

    def makeParsingError(self, message):
        """
        Creates a DocParsingError with the specified message.  The
        source code URL, row, and column are set to the node
        corresponding values.
        """
        return DocParsingError(
            self.getSourceURL(), 
            self.getSourceRow(),
            self.getSourceColumn(),
            message)

    def drillIndex(self, branch = None):
        """
        Recusrively searches for the base of the index, and then makes
        it.  While doing this, it records the visited nodes in BRANCH,
        so that the correct index path can be opened when the index is
        made.
        """
        if branch is None:
            branch = [] 
        branch.append(self)
        if self.parent:
            return self.parent.drillIndex(branch)
        return None

    def makeIndex(self, branch):
        """
        Recusrively makes the HTML index, opening the branch BRANCH.
        By default, it simply calls itself on all children.
        """
        html = []
        [html.extend(c.makeIndex(branch)) for c in self.children]
        return html

    def getPublishDirName(self):
        """
        Returns the parent publish dir name.
        """
        if self.parent:
            return self.parent.getPublishDirName()
        return ""

    def getPublishFileName(self):
        """
        Returns NONE.
        """
        return None

    def getPublishURL(self):
        """
        Returns NONE.
        """
        return None

    def getRelativePublishURL(self, fromNode = None):
        """
        Returns the publish URL relative to FROMNODE. If FROMNODE is
        not specified, FROMNODE is set to the first ancestor of type
        DocSite.
        """
        if fromNode is None:
            fromNode = self.findAncestors(DocSite)[0]
        return calcRelURL(self.getPublishURL(), fromNode.getPublishURL())

    def publish(self):
        """
        Recursively calls PUBLISH on its children.
        """
        [c.publish() for c in self.getChildren()]
        return None

# --------------------------------------------------------------------    
class Generator:
# --------------------------------------------------------------------
    def __init__(self, rootDir):
        ensureDir(rootDir)
        self.fileStack = []
        self.dirStack = rootDir

    def open(fileName):
        filePath = os.path.join(self.dirStack[-1], fileName)
        fid = open(filePath, "w")
        self.fileStack.append(fid)
        
    def putString(str):
        fid = self.fileStack[-1]
        write(fid, str)
    
    def close():
        close(self.fileStack.pop())
        
    def changeDir(dirName):
        currentDir = os.dirStack[-1]
        newDir = os.path.join(os.dirStack, dirName)
        ensuredir(newDir)
        
    def parentDir():
        os.dirStack.pop()

# --------------------------------------------------------------------    
class DocInclude(DocNode):
# --------------------------------------------------------------------
    def __init__(self, attrs, URL, locator):
        DocNode.__init__(self, attrs, URL, locator)
        if not attrs.has_key("src"):
            raise self.makeParsingError("include missing 'src' attribute")
        self.fileName = attrs["src"]

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:include src=%s>" \
            % xml.sax.saxutils.quoteattr(self.fileName)

# --------------------------------------------------------------------    
class DocDir(DocNode):
# --------------------------------------------------------------------
    def __init__(self, attrs, URL, locator):
        DocNode.__init__(self, attrs, URL, locator)
        if not attrs.has_key("name"):
            raise self.makeParsingError("dir tag missing 'name' attribute")
        self.dirName = attrs["name"]

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:dir name=%s>" \
            % xml.sax.saxutils.quoteattr(self.dirName)

    def getPublishDirName(self):        
        return self.parent.getPublishDirName() + self.dirName + "/"

# --------------------------------------------------------------------    
class DocHtmlContent(DocNode):
# --------------------------------------------------------------------
    def xExpand(self, pageNode):
        return None

    def xCopy(self):
        node = self.copy()
        node.children = []
        [node.adopt(x.xCopy()) for x in self.children]
        return node

# --------------------------------------------------------------------    
class DocHtmlText(DocHtmlContent):
# --------------------------------------------------------------------
    def __init__(self, text, cdata = None):
        DocHtmlContent.__init__(self, {}, None, None)
        if cdata is None: cdata = False
        self.text = text
        self.cdata = cdata

    def __str__(self):        
        return DocNode.__str__(self) + ":text:'" + \
            self.text.encode('utf-8').encode('string_escape') + "'" 

    def xExpand(self, pageNode):
        expansion = []
        last = 0
        for m in re.finditer("%\w+;", self.text):
            if last <= m.start() - 1:
                textChunk = self.text[last : m.start() - 1]
                expansion.append(DocHtmlText(textChunk, cdata = self.cdata))
            last = m.end()

            nodes = []
            label = self.text [m.start() + 1 :m.end() - 1]
            if label == "content":
                [nodes.extend(x.xExpand(pageNode))
                 for x in pageNode.getHtmlContent()]

            elif label == "pagestyle":
                for s in pageNode.findChildren(DocPageStyle):
                    sa = s.getAttributes()
                    if sa.has_key("type"):
                        type = sa["type"]
                    else:
                        type = "text/css"
                    if sa.has_key("href"):
                        href = sa["href"]
                        nodes.append(DocHtmlElement("link", {"href":href, "type":type, "rel":"stylesheet"}))
                    h = s.findChildren(DocHtmlContent)
                    if len(h) > 0:
                        style = DocHtmlElement("style", {"type":type})
                        [style.adopt(x.xExpand(pageNode)) for x in h]
                        nodes.append(style)

            elif label == "pagescript":
                for s in pageNode.findChildren(DocPageScript):
                    sa = s.getAttributes()
                    if sa.has_key("type"):
                        type = sa["type"]
                    else:
                        type = "text/javascript"
                    if sa.has_key("src"):
                        src = sa["src"]
                        nodes.append(DocHtmlElement("script", {"src":src, "type":type}))
                    h = s.findChildren(DocHtmlContent)
                    if len(h) > 0:
                        script = DocHtmlElement("script", {"type":type})
                        [script.adopt(x.xExpand(pageNode)) for x in h]
                        nodes.append(script)

            elif label == "navigation":
                nodes.extend(pageNode.drillIndex())

            else:
                print "warning: ignoring " + label
            expansion.extend(nodes)
        if last < len(self.text):
            textChunk = self.text[last:]
            expansion.append(DocHtmlText(textChunk, cdata = self.cdata))
        return expansion

    def toHtmlCode(self):
        if not self.cdata:
            return xml.sax.saxutils.escape(self.text, mapUnicodeToHtmlEntity)
        else:
            return self.text.encode('utf-8')

# --------------------------------------------------------------------    
class DocHtmlElement(DocHtmlContent):
# --------------------------------------------------------------------
    def __init__(self, tag, attrs, URL = None, locator = None):
        DocHtmlContent.__init__(self, attrs, URL, locator)
        self.tag = tag
        
    def __str__(self):
        str = "<html:" + self.tag
        for k, v in self.attrs.items():
            str = str + " " + k + "='" + xml.sax.saxutils.escape(v) + "'"
        str = str + ">"
        return DocNode.__str__(self) + ":" + str

    def toHtmlCode(self):
        htmlCode = "<" + self.tag
        for k, v in self.attrs.items():
            if k == "href":
                v = calcRelHref(v, self)
            htmlCode += " " + k + "=" + xml.sax.saxutils.quoteattr(v, mapUnicodeToHtmlEntity)
        htmlCode += ">" + "".join(
            [x.toHtmlCode() for x in self.findChildren(DocHtmlContent)])
        htmlCode += "</" + self.tag + ">"
        return htmlCode

    def getPublishURL(self):
        pageNode = self.findAncestors(DocPage)[0]
        return pageNode.getPublishURL() + "#" + self.id

    def xExpand(self, pageNode):
        node = self.copy()
        node.attrs = {}
        for k, v in self.attrs.iteritems():
            v_ = ""
            last = 0
            for m in re.finditer("%[\w:]+;", v):
                if last <= m.start() - 1:
                    v_ += v[last : m.start() - 1]
                last = m.end()

                directive = v [m.start() + 1 : m.end() - 1]                                
                mo = re.match('pathto:(\w*)', directive)
                if mo:
                    id = mo.group(1)
                    href = calcRelHref(id, self)
                    v_ += href
                else:
                    raise self.makeParsingError('unknown directive ''%s''' % directive)
            if last < len(v): v_ += v[last:]
            node.attrs[k] = v_

        node.children = [] 
        for c in self.children:
            node.adopt(c.xExpand(pageNode))
        return [node]

# --------------------------------------------------------------------    
class DocWithHtmlContent(DocNode):
# --------------------------------------------------------------------
    def getHtmlContent(self):
        return self.findChildren(DocHtmlContent)

    def getCopyOfHtmlContent(self):
        nodes = []
        [nodes.append(x.xCopy()) for x in self.findChildren(DocHtmlContent)]
        return nodes

    def toHtmlCode(self):
        return "".join([x.toHtmlCode() for x in self.getHtmlContent()])

# --------------------------------------------------------------------    
class DocExpandedContent(DocWithHtmlContent):
# --------------------------------------------------------------------
    def __init__(self):
        DocWithHtmlContent.__init__(self, {}, None, None)

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:content>" \
            % xml.sax.saxutils.escape(self.dirName)

    def publish(self):
        pass

# --------------------------------------------------------------------    
class DocTemplate(DocWithHtmlContent):
# --------------------------------------------------------------------
    def __init__(self, attrs, URL, locator):
        DocNode.__init__(self, attrs, URL, locator)

# --------------------------------------------------------------------    
class DocPageStyle(DocWithHtmlContent):
# --------------------------------------------------------------------
    def __init__(self, attrs, URL, locator):
        DocNode.__init__(self, attrs, URL, locator)

# --------------------------------------------------------------------
class DocPageScript(DocWithHtmlContent):
# --------------------------------------------------------------------
    def __init__(self, attrs, URL, locator):
        DocNode.__init__(self, attrs, URL, locator)

# --------------------------------------------------------------------    
class DocPage(DocWithHtmlContent):
# --------------------------------------------------------------------
    counter = 0

    def __init__(self, attrs, URL, locator):
        DocNode.__init__(self, attrs, URL, locator)
        DocPage.counter = 1 + DocPage.counter
        self.templateID = "template.default"
        self.name  = "page%d" % DocPage.counter
        self.title = "untitled"

        for k, v in self.attrs.items():
            if k == 'src':
                self.title = v
            elif k == 'name':
                self.name = v
            elif k == 'id':
                pass
            elif k == 'title':
                self.title = v        
            else:                
                raise self.makeParsingError("page cannot have '%s' attribute" % k)

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:page name='%s' title='%s'>" \
            % (xml.sax.saxutils.escape(self.name), 
               xml.sax.saxutils.escape(self.title))

    def getPublishFileName(self):
        return self.name + ".html"

    def getPublishURL(self):
        siteNode = self.findAncestors(DocSite)[0]
        return siteNode.getPublishURL() + \
            self.getPublishDirName() + \
            self.getPublishFileName()

    def publish(self):

        templateNode = nodeIndex[self.templateID]

        content = DocExpandedContent()
        [content.adopt(x) for x in templateNode.getCopyOfHtmlContent()]
        self.adopt(content)

        html = [] 
        [html.extend(x.xExpand(self)) for x in content.getHtmlContent()]

        URL = self.getPublishURL()
        dirName  = os.path.join('html', self.getPublishDirName())
        fileName = self.getPublishFileName()
        pathName = os.path.join(dirName, fileName)

        # make directory
        try:
            ensureDir(dirName)
        except Exception, (e):
            raise self.makeParsingError("cannot create directory '%s'" % dirName)
        print "writing page '%s' to '%s'" % (self.name, pathName)
        f = open(pathName, "w")
        [f.write(x.toHtmlCode()) for x in html]
        f.close()

        # Do not forget to publish the rest
        [x.publish() for x in self.findChildren(DocHtmlContent)]

        return None

    def makeIndex(self, branch):
        li = DocHtmlElement('li', {})
        a = DocHtmlElement('a', {'href': self.id})
        a.adopt(DocHtmlText(self.title))
        li.adopt(a)
        if self in branch:
            ul = DocHtmlElement('ul', {})
            for c in self.children:
                [ul.adopt(x) for x in c.makeIndex(branch)]
            li.adopt(ul)
        return [li]

# --------------------------------------------------------------------    
class DocSite(DocNode):
# --------------------------------------------------------------------
    def __init__(self, attrs, URL, locator):
        DocNode.__init__(self, attrs, URL, locator)
        self.siteURL = "http://www.foo.org/"

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:site>"

    def getPublishURL(self):
        return self.siteURL

    def getPublishDirName(self):
        return ""

    def drillIndex(self, branch):
        ul = DocHtmlElement('ul', {})
        for c in self.children:
            [ul.adopt(x) for x in c.makeIndex(branch)]
        return [ul]

# --------------------------------------------------------------------    
class DocHandler(ContentHandler):
# --------------------------------------------------------------------
    
    def __init__(self):
        ContentHandler.__init__(self)
        self.rootNode = None
        self.stack = []
        self.locatorStack = []
        self.fileNameStack = []
        self.verbosity = 1
        self.inCDATA = False

    def resolveEntity(self, publicid, systemid):
        """
        Resolve XML entities by mapping to a local copy of the (X)HTML DTDs.
        """
        return open(os.path.join('dtd/xhtml1', 
                                 systemid[systemid.rfind('/')+1:]), "rb")

    def startElement(self, name, attrs):
        # convert attrs to an actual dictionary
        attrs_ = {}
        for k, v in attrs.items():
            attrs_[k] = v
        attrs = attrs_
        
        if name == "include":
            if not attrs.has_key("src"):
                raise self.makeParsingError("include missing 'src' attribute")
            fileName = attrs["src"]
            if self.verbosity > 0:
                print "sourcing '%s'" % fileName
            self.load(fileName)
            return

        URL = self.getCurrentFileName()
        locator = self.getCurrentLocator()

        if len(self.stack) == 0:
            parent = None
        else:            
            parent = self.stack[-1]
        node = None

        if   name == "site":
            node = DocSite(attrs, URL, locator)
        elif name == "page":
            node = DocPage(attrs, URL, locator)
        elif name == "dir":
            node = DocDir(attrs, URL, locator)
        elif name == "template":
            node = DocTemplate(attrs, URL, locator)
        elif name == "pagestyle":
            node = DocPageStyle(attrs, URL, locator)
        elif name == "pagescript":
            node = DocPageScript(attrs, URL, locator)
        else:
            node = DocHtmlElement(name, attrs, URL, locator)
            
        if parent: parent.adopt(node)
        self.stack.append(node)
        
    def endElement(self, name): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        if name == "include":
            return
        node = self.stack.pop()
        if len(self.stack) == 0:
            self.rootNode = node

    def load(self, fileName): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        self.fileNameStack.append(fileName)
        parser = xml.sax.make_parser()
        parser.setContentHandler(self)
        parser.setEntityResolver(self)
        parser.setProperty(xml.sax.handler.property_lexical_handler, self)
        parser.parse(fileName)

    def setDocumentLocator(self, locator): # ~~~~~~~~~~~~~~~~~~~~~~~~~
        self.locatorStack.append(locator)

    def getCurrentLocator(self): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        if len(self.locatorStack) > 0:
            return self.locatorStack[-1]
        else:
            return None

    def characters(self, content):
        parent = self.stack[-1]
        node = DocHtmlText(content, cdata = self.inCDATA)
        parent.adopt(node)

    def ignorableWhitespace(self, ws):
        self.characters(ws)
    
    def getCurrentFileName(self): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        return self.fileNameStack[-1]

    def endDocument(self):
        self.locatorStack.pop()
        self.fileNameStack.pop()

    def startCDATA(self):
        self.inCDATA = True

    def endCDATA(self):
        self.inCDATA = False

    def comment(self, body): pass
    def startEntity(self, name): pass
    def endEntity(self, name): pass
    def startDTD(self, name, public_id, system_id): pass
    def endDTD(self): pass

# --------------------------------------------------------------------    
if __name__ == '__main__':
# --------------------------------------------------------------------
    fileName = sys.argv[1]
    handler = DocHandler()
    try:
        handler.load(fileName)
    except (DocParsingError, xml.sax.SAXParseException), (e):
        print e
        sys.exit(-1)
    #print "== Index Content =="
    # dumpIndex()
    #print
    print "== Node Tree =="
    handler.rootNode.dump()    

    print "== Publish =="
    handler.rootNode.publish()
    sys.exit(0)
