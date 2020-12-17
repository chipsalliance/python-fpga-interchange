from fpga_interchange.annotations import AnnotationCache


def dereference_value(annotation_type, value, root):
    if annotation_type.type == 'root':
        return getattr(root, annotation_type.field)[value]
    else:
        assert annotation_type.type == 'parent'
        raise NotImplementedError()


class Enumerator():
    def __init__(self):
        self.values = []
        self.map = {}

    def get_index(self, value):
        index = self.map.get(value, None)
        if index is None:
            self.values.append(value)
            return len(self.values) - 1
        else:
            return index

    def write_message(self, message, field):
        list_builder = message.init(field, len(self.values))

        for idx, value in enumerate(self.values):
            list_builder[idx] = value


def init_implementation(annotation_value):
    if annotation_value.type == 'enumerator':
        return Enumerator()
    else:
        raise NotImplementedError()


def to_yaml(struct_reader, root=None, annotation_cache=None):
    if root is None:
        root = struct_reader
        annotation_cache = AnnotationCache()

    schema = struct_reader.schema

    out = {}

    fields = set(schema.non_union_fields)
    if schema.union_fields:
        fields.add(struct_reader.which())

    for field in schema.fields_list:
        key = field.proto.name
        if key not in fields:
            continue

        which = field.proto.which()
        if which == 'group':
            group = getattr(struct_reader, key)
            inner_key = group.which()
            value = getattr(group, inner_key)

            set_value = lambda value: out.update({key: {inner_key: value}})
            field_proto = field.schema.fields[inner_key].proto
        else:
            assert which == 'slot', which
            value = getattr(struct_reader, key)
            set_value = lambda value: out.update({key: value})
            field_proto = field.proto

        deference_fun = None
        hide_field = False
        for annotation in field_proto.annotations:
            _, annotation_value = annotation_cache.get_annotation_value(
                annotation)
            if annotation_cache.is_reference_annotation(annotation):
                assert deference_fun is None
                deference_fun = lambda value: dereference_value(annotation_value, value, root)

            if annotation_cache.is_implementation_annotation(annotation):
                if annotation_value.hide:
                    hide_field = True

        if hide_field:
            continue

        if deference_fun is None:
            deference_fun = lambda value: value

        field_type = field_proto.slot.type

        field_which = field_type.which()
        if field_which == 'struct':
            set_value(to_yaml(value, root, annotation_cache))
        elif field_which == 'list':
            list_type = field_type.list.elementType
            list_which = list_type.which()

            data = []
            if list_which == 'struct':
                for elem in value:
                    data.append(to_yaml(elem, root, annotation_cache))
            else:
                for elem in value:
                    data.append(deference_fun(elem))

            set_value(data)
        elif field_which == 'void':
            set_value(None)
        elif field_which == 'enum':
            set_value(value._as_str())
        else:
            assert field_which in [
                'bool',
                'int8',
                'int16',
                'int32',
                'int64',
                'uint8',
                'uint16',
                'uint32',
                'uint64',
                'float32',
                'float64',
                'text',
            ], field_which

            set_value(deference_fun(value))

    return out


def reference_value(annotation_type, value, root):
    if annotation_type.type == 'root':
        return root[1][annotation_type.field].get_index(value)
    else:
        assert annotation_type.type == 'parent'
        raise NotImplementedError()


def from_yaml(message, data, root=None, annotation_cache=None):
    obj = [data, {}]
    if root is None:
        root = obj
        annotation_cache = AnnotationCache()

    schema = message.schema

    fields = set(schema.non_union_fields)
    defered_fields = set()

    union_field = None
    for field in schema.union_fields:
        if field in data:
            assert union_field is None, (field, union_field)
            union_field = field
            fields.add(field)

    for field in schema.fields_list:
        key = field.proto.name
        if key not in fields:
            continue

        which = field.proto.which()
        if which != 'slot':
            continue

        for annotation in field.proto.annotations:
            _, annotation_value = annotation_cache.get_annotation_value(
                annotation)
            if annotation_cache.is_implementation_annotation(annotation):
                if annotation_value.hide:
                    obj[1][key] = init_implementation(annotation_value)
                    defered_fields.add(key)

    for field in defered_fields:
        assert field not in data

    for field in schema.fields_list:
        key = field.proto.name
        if key not in fields or key in defered_fields:
            continue

        which = field.proto.which()
        if which == 'group':
            keys = list(data[key].keys())
            assert len(keys) == 1, keys
            inner_key = keys[0]
            builder = getattr(message, key)
            field_data = data[key][inner_key]
            key = inner_key
            field_proto = field.schema.fields[inner_key].proto
        else:
            builder = message
            field_data = data[key]
            field_proto = field.proto

        reference_fun = None
        hide_field = False
        for annotation in field_proto.annotations:
            _, annotation_value = annotation_cache.get_annotation_value(
                annotation)
            if annotation_cache.is_reference_annotation(annotation):
                assert reference_fun is None
                reference_fun = lambda value: reference_value(annotation_value, value, root)

            if annotation_cache.is_implementation_annotation(annotation):
                if annotation_value.hide:
                    hide_field = True

        if reference_fun is None:
            reference_fun = lambda value: value

        if hide_field:
            continue

        field_type = field_proto.slot.type
        field_which = field_type.which()
        if field_which == 'struct':
            builder.init(key)
            from_yaml(
                getattr(builder, key), field_data, root, annotation_cache)
        elif field_which == 'list':
            list_builder = builder.init(key, len(field_data))
            list_type = field_type.list.elementType
            list_which = list_type.which()

            if list_which == 'struct':
                for elem_builder, elem in zip(list_builder, field_data):
                    from_yaml(elem_builder, elem, root, annotation_cache)
            else:
                for idx, elem in enumerate(field_data):
                    list_builder[idx] = reference_fun(elem)
        elif field_which == 'void':
            assert field_data is None
            setattr(builder, key, None)
        elif field_which == 'enum':
            setattr(builder, key, field_data)
        else:
            assert field_which in [
                'bool',
                'int8',
                'int16',
                'int32',
                'int64',
                'uint8',
                'uint16',
                'uint32',
                'uint64',
                'float32',
                'float64',
                'text',
            ], field_which

            setattr(builder, key, reference_fun(field_data))

    for field in defered_fields:
        obj[1][field].write_message(message, field)
