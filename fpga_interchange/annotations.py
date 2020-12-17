from fpga_interchange.capnp_utils import get_module_from_id

def get_first_enum_field_display_name(annotation_value, parser=None):
    field0_proto = annotation_value.schema.fields_list[0].proto
    if field0_proto.which() != 'slot':
        return None

    field0_type = field0_proto.slot.type
    if field0_type.which() != 'enum':
        return None

    e = get_module_from_id(field0_type.enum.typeId, parser)
    return e.schema.node.displayName

def get_annotation_value(annotation, parser=None):
    """ Get annotation value from an annotation.  Schema that the annotation belongs too is required. """

    annotation_module = get_module_from_id(annotation.id, parser)
    name = annotation_module.__name__

    which = annotation.value.which()
    if which == 'struct':
        annotation_type = annotation_module._nodeSchema.node.annotation.type

        assert annotation_type.which() == 'struct'
        struct_type_id = annotation_type.struct.typeId
        annotation_struct_type = get_module_from_id(struct_type_id, parser)

        return name, annotation.value.struct.as_struct(annotation_struct_type)
    elif which == 'void':
        return name, None
    elif which in [
        'bool',
        'float32',
        'float64',
        'int16',
        'int32',
        'int64',
        'int8',
        'text',
        'uint16',
        'uint32',
        'uint64',
        'uint8']:
        return name, getattr(annotation.value, which)
    else:
        raise NotImplementedError('Annotation of type {} not supported yet.'.format(which))


class AnnotationCache():
    def __init__(self, parser=None):
        self.parser = parser

        self.annotation_values = {}
        self.annotation_display_names = {}

    def get_annotation_value(self, annotation):
        if annotation.id not in self.annotation_values:
            self.annotation_values[annotation.id] = get_annotation_value(annotation, self.parser)

        return self.annotation_values[annotation.id]

    def is_first_field_display_name(self, annotation, expected_display_name):
        if annotation.id not in self.annotation_display_names:
            _, annotation_value = self.get_annotation_value(annotation)
            self.annotation_display_names[annotation.id] = get_first_enum_field_display_name(annotation_value, self.parser)

        display_name = self.annotation_display_names[annotation.id]
        if display_name is None:
            return False
        return display_name == expected_display_name

    def is_reference_annotation(self, annotation):
        return self.is_first_field_display_name(annotation, 'References.capnp:ReferenceType')


    def is_implementation_annotation(self, annotation):
        return self.is_first_field_display_name(annotation, 'References.capnp:ImplementationType')
