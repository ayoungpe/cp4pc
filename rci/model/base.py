"""Core model entries that can be used by many implementations"""
import StringIO
try:
    from xml.etree import cElementTree as ET
except:
    try:
        from xml.etree import ElementTree as ET
    except:
        import ElementTree as ET

def _dict2xmlattr(d):
    return " ".join('{key}="{value}"'.format(key=key, value=value)
                    for key, value in d.items())


def _get_attr_desc_xml(tree_node):
    """Get xml for attributes a node"""
    attrs = getattr(tree_node, 'attrs', [])

    sio = StringIO.StringIO()
    for attribute in attrs:
        # open tag
        sio.write('<attr name="{name}" desc="{desc}"'
                  .format(name=attribute.name,
                          desc=attribute.desc))
        if attribute.values is not None:
            sio.write(">")
            for value in attribute.values:
                sio.write('<value value="{value}" desc="{desc}"'
                          '  dscr_avail="true" />'
                          .format(value=value.name, desc=value.desc))
            sio.write("</attr>")
        else:
            sio.write(" />")  # just close the attr tag
    return sio.getvalue()


def _get_error_desc_xml(tree_node):
    """Get xml for errors on a node"""
    errors = getattr(tree_node, 'errors', {})
    error_text = ""
    for error_id, error_desc in errors.iteritems():
        error_text += ('<error_descriptor id="{id}" desc="{desc}" />'
                       .format(id=error_id, desc=error_desc))
    return error_text


class DTYPE(object):
    """Enumeration of predefined data types that can be used"""

    NONE = "none"
    STRING = "string"
    MULTILINE_STRING = "multiline_string"
    PASSWORD = "password"
    INT32 = "int32"
    UINT32 = "uint32"
    HEX32 = "hex32"
    xHEX32 = "0x_hex32"
    FLOAT = "float"
    ENUM = "enum"
    ENUM_MULTI = "enum_multi"
    ON_OFF = "on_off"
    BOOLEAN = "boolean"
    IPV4 = "ipv4"
    FQDNV4 = "fqdnv4"
    FQDNV6 = "fqdnv6"
    MULTI = "multi"
    LIST = "list"
    RAW_DATA = "raw_data"
    XBEE_EXT_ADDR = "xbee_ext_addr"
    FILE_NAME = "file_name"
    MAC_ADDR = "mac_addr"
    DATETIME = "datetime"


class RCIAttribute(object):
    """Encapsulate information describing an RCI attribute"""

    def __init__(self, name, desc, values=None):
        self.name = name
        self.desc = desc
        self.values = values


class RCIAttributeValue(object):
    """Encapsulate information describing an RCI attribute value"""

    def __init__(self, name, desc, target_node):
        self.name = name
        self.desc = desc
        self.target_node = target_node


class Node(object):
    """Base node class, must have at least a name"""

    desc = None

    def __init__(self, name):
        assert type(self) != Node, "Node is an abstract class"
        self.name = name

    def _cdata(self, content):
        """Wrap provided content in a CDATA declaration"""
        return "<![CDATA[{content}]]>".format(content=content)

    def _xml_tag(self, body=None, attributes=None):
        """Wrap body and attributes in xml tag with this Node's name"""
        attrs = ""
        if attributes is not None:
            attrs = " " + " ".join('%s="%s"' % (key, value)
                             for key, value in attributes.iteritems())
        if body is not None and len(body) > 0:
            return "<%s%s>%s</%s>" % (self.name, attrs, body, self.name)
        else:
            return "<%s%s />" % (self.name, attrs)

    def _xml_error(self, error_id, error_desc=None, hint=None):
        """Build an XML rci error with the provided information"""
        if (error_desc is None
            and len(self.errors) > 0):
            error_desc = self.errors[error_id]
        attrs = {
            'id': error_id,
            'desc': error_desc,
        }
        if hint is not None:
            attrs['hint'] = hint
        attrs_text = " ".join('{key}="{val}"'.format(key=key, val=val)
                              for key, val in attrs.items())
        return "<error {attrs_text} />".format(attrs_text=attrs_text)

    def handle_xml(self, etree_node):
        return self.toxml()

    def toxml(self):
        """Return a representation of this node in XML form"""
        return self._xml_tag()


class BranchNode(Node):
    """A node that has only children (no data)

    If looking at the RCI spec, this matches up (in general) with the
    "descriptor" element.
    """

    # required attrs
    desc = ""

    # optional descriptor attributes
    attrs = None
    access = None
    dscr_avail = None
    dformat = None
    errors = None

    def __init__(self, node_name, desc=None):
        self.name = node_name
        self.children = []
        if desc is not None:
            self.desc = desc
        if self.attrs is None:
            self.attrs = {}
        if self.errors is None:
            self.errors = {}

    def __iter__(self):
        return iter(self.children[:]) # NOTE: copy to make iterator thread safe

    def _tree_match(self, xml_node, device_node):
        for child in device_node:
            ret = self._tree_match_helper(xml_node, child)
            if ret is not None:
                return ret
        return None

    def _tree_match_helper(self, xml_node, device_node):
        """For an xml node, return the associated device_tree node

        The search is performed breadth first as this is typically the
        behavior one would want for this kind of search (otherwise, you
        can change the root for the search).

        If there does not appear to be a match for the provided xml node
        then the function will return None.  The match acts on the provided
        xml node and all its children, with attribute matching as well
        if given in the xml tree.

        """
        # build the attrib sets used for comparing nodes
        xml_node_attrib_set = set(xml_node.attrib.items())
        device_node_attrib_set = set()
        for attribute in getattr(device_node, 'attrs', []):
            for value in attribute.values:
                device_node_attrib_set.add((attribute.name, value.name))

        # Are we done?  Do our base check first before recursing
        # we call this a match if the specified attributes in the
        # xml are a subset of the set of all possible attribute/value
        # pairs on the target
        if (xml_node_attrib_set <= device_node_attrib_set and
             device_node.name == xml_node.tag):
            # this node matches, determine if we need to recurse
            # down the tree further
            if len(xml_node.getchildren()) == 0:
                return device_node  # bingo!
            else:
                # not done yet, recurse on all children
                assert len(xml_node.getchildren()) == 1
                for child in device_node:
                    res = self._tree_match_helper(xml_node.getchildren()[0],
                                                  child)
                    if res is not None:
                        return res

                # no child matces, not a match
                return None

        # not a match
        return None

    def get(self, name, default=None):
        for child in self: # NOTE: should be thread-safe, iterator makes copy
            if child.name == name:
                return child
        return default

    def attach(self, child):
        """Attach the child, return reference to self for chaining"""
        self.children.append(child)
        return self

    def to_descriptor_xml(self, xml_query_node):
        attrs = {
            'element': self.name,
            'desc': self.desc,
        }
        if self.dscr_avail is not None:
            attrs['dscr_avail'] = self.desr_avail
        if self.access is not None:
            attrs['access'] = self.access
        if self.dformat is not None:
            attrs['format'] = self.dformat

        child_descriptor_xml = ''.join(x.to_descriptor_xml(None)
                                       for x in self.children)
        attr_text = " ".join('{key}="{value}"'.format(key=key, value=value)
                             for key, value in attrs.items())

        return ("<descriptor {attr_text}>{attributes}"
                "{error_text}{children}</descriptor>"
                .format(attr_text=attr_text,
                        attributes=_get_attr_desc_xml(self),
                        error_text=_get_error_desc_xml(self),
                        children=child_descriptor_xml))

    def handle_xml(self, xml_tree):
        if len(xml_tree) == 0:
            return self.toxml()
        else:
            output = ""
            for child in xml_tree:
                match_node = self._tree_match(child, self)
                if match_node:
                    output += match_node.toxml()
                else:
                    output += '' #TODO: what to do if there is no match?
            return self._xml_tag(output)

    def toxml(self, attributes=None):
        return self._xml_tag(
            body=''.join(child.toxml() for child in self.children),
            attributes=attributes)


class TargetNode(BranchNode):
    """A Node that is used for do_command."""
    def __init__(self, name, desc='', callback=None):
        BranchNode.__init__(self, name, desc)
        self.callback = callback

    def to_descriptor_xml(self, xml_query_node):
        child_descriptor_xml = ''.join(x.to_descriptor_xml(None)
                                       for x in self.children)        
        return ('<attr name="target" desc="{desc}" value="{target}">'
                '{child}</attr>'
                .format(target=self.name,
                        desc=self.desc,
                        child=child_descriptor_xml))
    
    def handle_xml(self, xml_tree):
        if self.callback:
            # pass XMl as a string to the callback
            xml_payload = xml_tree.text # characters before first child
            for parameter in list(xml_tree):
                xml_payload += ET.tostring(parameter)
            xml_payload += xml_tree.tail # characters after last element
            return self.callback(xml_payload)
        else:
            ret = ''
            for xml_child in xml_tree:
                child_node = self.get(xml_child.tag)
                if child_node:
                    ret += child_node.handle_xml(xml_child)
                else:
                    pass #TODO: return an error when there is an unsupported command
            return ret
                
            #return BranchNode.handle_xml(self, xml_tree)
       

class LeafNode(Node):
    """A Node that has no children (just data)

    This element most closely matches up with "element"s in
    the RCI descriptor language.
    """

    #: attributes available on tag (empty dict not good as it will
    #: likely get mutated across instances)
    attrs = None

    #: short description, can be overriden in subclass/instance
    desc = None

    #: data type, can be overriden in subclass/instance
    dtype = DTYPE.STRING

    #: minimum value, only valid for some dtypes
    dmin = None

    #: maximium value, only valid for some dtypes
    dmax = None

    #: default value: optional
    default = None

    #: format (optional)
    dformat = None

    #: access (default: read_write)
    access = "read_only"

    #: units (optional)
    units = None

    #: errors (dictionary of id -> desc pairs)
    errors = None

    def __init__(self, name):
        Node.__init__(self, name)
        if self.attrs is None:
            self.attrs = {}
        if self.errors is None:
            self.errors = {}

    def to_descriptor_xml(self, xml_query_node):
        attrs = {
            'desc': self.desc,
            'name': self.name,
            'type': self.dtype,
        }

        # fallback on name if no desc
        if self.desc is None:
            attrs['desc'] = self.name

        if self.default is not None:
            attrs['default'] = self.default
        if self.dmin is not None:
            attrs['min'] = self.dmin
        if self.dmax is not None:
            attrs['max'] = self.dmax
        if self.dformat is not None:
            attrs['format'] = self.dformat
        if self.access is not None:
            attrs['access'] = self.access
        if self.units is not None:
            attrs['units'] = self.units

        # TODO: add enum descriptor support
        if self.errors is None and self.attrs is None:
            return ('<element {attrs_text} />'
                    .format(attrs_text=_dict2xmlattr(attrs)))
        else:
            return ("<element {attrs_text}>{attributes}{error_text}</element>"
                    .format(attrs_text=_dict2xmlattr(attrs),
                            attributes=_get_attr_desc_xml(self),
                            error_text=_get_error_desc_xml(self)))

    def toxml(self, body=None, attributes=None):
        return self._xml_tag(body=body, attributes=attributes)


class SimpleLeafNode(LeafNode):
    """Simple leaf node that wraps accessor/setter functions for the data

    The accessor/setter params are functions having the following signature::

       accessor() ->
          str/None: body OR
          (str/None: body, dict/None: attributes)

       setter(str/None: body, dict/None: attributes) ->
          None

    """

    def __init__(self, name, accessor=None, setter=None,
                 dtype=None, desc=None):
        LeafNode.__init__(self, name)
        self.accessor = accessor
        self.setter = setter
        if dtype is not None:
            self.dtype = dtype
        if desc is not None:
            self.desc = desc

    def toxml(self):
        if self.accessor is not None:
            value = self.accessor()
            if isinstance(value, str):
                return self._xml_tag(body=value)
            else:
                body, attributes = self.accessor()
                return self._xml_tag(body=body, attributes=attributes)
        else:
            return self._xml_tag()