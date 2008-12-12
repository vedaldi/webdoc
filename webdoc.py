#!/usr/bin/python
import xml.sax
import xml.sax.saxutils
import re
import sys 
import random

from xml.sax.handler import ContentHandler
from xml.sax         import parse

nodeIndex   = { }

template = """
<html>
  <body>
   %content;
  </body>
</html>
"""

# --------------------------------------------------------------------    
def getUniqueNodeID():
# --------------------------------------------------------------------
    "Generate an unique ID for a node"
    while 1:
        id = "#%010d#" % int(random.random() * 1e10)
        if id not in nodeIndex: break
    return id

# --------------------------------------------------------------------    
def dumpIndex():
# --------------------------------------------------------------------
    for (id, node) in nodeIndex.iteritems():
      print node

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
    def __init__(self, parent, attrs, URL, locator):
        self.parent = parent
        self.children = []
        self.attrs = attrs
        self.sourceURL = None
        self.sourceRow = None
        self.sourceColumn = None
        if attrs.has_key('id'):
            self.id = attrs[id]
        else:
            self.id = getUniqueNodeID()
        if URL:
            if not URL is self.getSourceURL():
                self.sourceURL = URL
        if locator:
            self.sourceRow = locator.getLineNumber()
            self.sourceColumn = locator.getColumnNumber()
        nodeIndex[self.id] = self

    def isA(self, classInfo):
        return isinstance(self, classInfo)

    def adopt(self, orfan):
        self.children.append(orfan)

    def getID(self):
        return self.id

    def getSourceURL(self):
        if self.sourceURL: 
            return self.sourceURL
        elif self.parent:
            return self.parent.getSourceURL()
        else:
            return ""
        
    def getSourceColumn(self):
        if not self.sourceColumn is None: 
            return self.sourceColumn 
        elif self.parent:
            return self.parent.getSourceColumn()
        else:
            return -1 

    def getSourceRow(self):
        if not self.sourceRow is None: 
            return self.sourceRow 
        elif self.parent:
            return self.parent.getSourceRow()
        else:
            return -1

    def getDepth(self):
        if self.parent:
            return self.parent.getDepth() + 1
        else:
            return 0

    def __str__(self):
        return "%s:%d:%d:%s" % (self.getSourceURL(),
                                self.getSourceRow(),
                                self.getSourceColumn(),
                                self.getID())

    def dump(self):
        depth = self.getDepth()
        print " " * depth, self
        for x in self.children: x.dump()

    def makeParsingError(self, message):
        return DocParsingError(
            self.getSourceURL(), 
            self.getSourceRow(),
            self.getSourceColumn(),
            message)

    def render(self):
        data = ""
        for c in self.children:
            data = data + c.render()
        return data

    def getRootRelativeDirName(self):
        if self.parent:
            return self.parent.getRootRelativeDirName()

# --------------------------------------------------------------------    
class DocInclude(DocNode):
# --------------------------------------------------------------------
    def __init__(self, parent, attrs, URL, locator):
        DocNode.__init__(self, parent, attrs, URL, locator)
        if not attrs.has_key("src"):
            raise self.makeParsingError("include missing 'src' attribute")
        self.fileName = attrs["src"]

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:include src='%s'>" \
            % xml.sax.saxutils.escape(self.fileName)

# --------------------------------------------------------------------    
class DocDir(DocNode):
# --------------------------------------------------------------------
    def __init__(self, parent, attrs, URL, locator):
        DocNode.__init__(self, parent, attrs, URL, locator)
        if not attrs.has_key("name"):
            raise self.makeParsingError("dir tag missing 'name' attribute")
        self.dirName = attrs["name"]

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:dir name='%s'>" \
            % xml.sax.saxutils.escape(self.dirName)

    def getRootRelativeDirName(self):
        str = ""
        if self.parent:
            str = self.parent.getRootRelativeDirName()
        return str + self.dirName + "/"

# --------------------------------------------------------------------    
class DocText(DocNode):
# --------------------------------------------------------------------
    def __init__(self, parent, data):
        DocNode.__init__(self, parent, {}, None, None)
        self.data = data

    def __str__(self):        
        return DocNode.__str__(self) + "text:'" + \
            self.data.encode('utf-8').encode('string_escape') + "'"

    def render(self):
        return self.data

# --------------------------------------------------------------------    
class DocHtmlElement(DocNode):
# --------------------------------------------------------------------
    def __init__(self, parent, tag, attrs, URL, locator):
        DocNode.__init__(self, parent, attrs, URL, locator)
        self.tag = tag
        
    def __str__(self):
        str = "<html:" + self.tag
        for k, v in self.attrs.items():
            str = str + " " + k + "='" + xml.sax.saxutils.escape(v) + "'"
        str = str + ">"
        return DocNode.__str__(self) + ":" + str

    def render(self):
        str = "<" + self.tag
        for k, v in self.attrs.items():
            str = str + " " + k + "='" + xml.sax.saxutils.escape(v) + "'"
        str = str + ">\n"
        str = str + DocNode.render(self)
        str = str + "</" + self.tag + ">"
        return str

# --------------------------------------------------------------------    
class DocSite(DocNode):
# --------------------------------------------------------------------
    def __init__(self, parent, attrs, URL, locator):
        DocNode.__init__(self, parent, attrs, URL, locator)

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:site>"

    def getRootRelativeDirName(self):
        return "html/"

# --------------------------------------------------------------------    
class DocPage(DocNode):
# --------------------------------------------------------------------
    counter = 0

    def __init__(self, parent, attrs, URL, locator):
        DocNode.__init__(self, parent, attrs, URL, locator)
        DocPage.counter = 1 + DocPage.counter
        self.title = "untitled"
        self.name  = "page%d" % DocPage.counter

        for k, v in self.attrs.items():
            if k == 'src':
                self.title = v
            if k == 'name':
                self.name = v
            else:
                raise self.makeParsingError("page cannot have '%s' attribute" % k)

    def __str__(self):        
        return DocNode.__str__(self) + ":<web:page name='%s' title='%s'>" \
            % (xml.sax.saxutils.escape(self.name), 
               xml.sax.saxutils.escape(self.title))

    def render(self):
        content = ""
        for c in self.children:
            if not c.isA(DocHtmlElement): continue
            content = content + c.render()

        code = template
        code = re.sub("%content;", content, code)

        # now subpages and other elements
        for c in self.children:
            if c.isA(DocHtmlElement): continue
            code = code + c.render()

        preamb = ""
        preamb = preamb + "<!-- name: %s -->\n" % self.name
        preamb = preamb + "<!-- title: %s -->\n" % self.title
        preamb = preamb + "<!-- dirName: %s -->\n" % self.getRootRelativeDirName()

        code = preamb + code
        return code

# --------------------------------------------------------------------    
class DocHandler(ContentHandler):
# --------------------------------------------------------------------
    
    def __init__(self): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        ContentHandler.__init__(self)
        self.rootNode = None
        self.stack = []
        self.locatorStack = []
        self.fileNameStack = []
        self.verbosity = 1

    def startElement(self, name, attrs): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~
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
            node = DocSite(parent, attrs, URL, locator)
        elif name == "page":
            node = DocPage(parent, attrs, URL, locator)
        elif name == "dir":
            node = DocDir(parent, attrs, URL, locator)
        else:
            node = DocHtmlElement(parent, name, attrs, URL, locator)
            
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
        xml.sax.parse(fileName, self)

    def setDocumentLocator(self, locator): # ~~~~~~~~~~~~~~~~~~~~~~~~~
        self.locatorStack.append(locator)

    def getCurrentLocator(self): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        if len(self.locatorStack) > 0:
            return self.locatorStack[-1]
        else:
            return None

    def characters(self, content): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        parent = self.stack[-1]
        node = DocText(parent, content)
        parent.adopt(node)
    
    def getCurrentFileName(self): # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        return self.fileNameStack[-1]

    def endDocument(self):
        self.locatorStack.pop()
        self.fileNameStack.pop()

# --------------------------------------------------------------------    
if __name__ == '__main__':
# --------------------------------------------------------------------
    fileName = sys.argv[1]
    handler = DocHandler()
    try:
        handler.load(fileName)
    except DocParsingError, (e):
        print e
        sys.exit(-1)
    print "== Index Content =="
    dumpIndex()
    print
    print "== Node Tree =="
    handler.rootNode.dump()    

    print "== Render =="
    print handler.rootNode.render()
    sys.exit(0)
