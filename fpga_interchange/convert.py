import argparse
import yaml
from yaml import CSafeLoader as SafeLoader, CDumper as Dumper
import json
from fpga_interchange.interchange_capnp import Interchange, read_capnp_file, write_capnp_file
import fpga_interchange.converters

SCHEMAS = ('device', 'logical', 'physical')
FORMATS = ('json', 'yaml', 'capnp')

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--schema', required=True, choices=SCHEMAS)
    parser.add_argument('--input_format', required=True, choices=FORMATS)
    parser.add_argument('--output_format', required=True, choices=FORMATS)
    parser.add_argument('input')
    parser.add_argument('output')

    args = parser.parse_args()


    schemas = Interchange(args.schema_dir)

    schema_map = {
            'device': schemas.device_resources_schema.Device,
            'logical': schemas.logical_netlist_schema.Netlist,
            'physical': schemas.logical_netlist_schema.PhysNetlist,
            }

    for schema_str in SCHEMAS:
        assert schema_str in schema_map

    schema = schema_map[args.schema]

    if args.input_format == 'capnp':
        with open(args.input, 'rb') as f:
            message = read_capnp_file(schema, f)
    elif args.input_format == 'json':
        with open(args.input, 'r') as f:
            json_data = json.load(f)

        message = schema.new_message()
        fpga_interchange.converters.from_yaml(message, json_data)
    elif args.input_format == 'yaml':
        with open(args.input, 'r') as f:
            yaml_string = f.read()

        yaml_data = yaml.load(yaml_string, Loader=SafeLoader)
        message = schema.new_message()
        fpga_interchange.converters.from_yaml(message, json_data)
    else:
        assert False, 'Invalid input format {}'.format(args.input_format)

    if args.output_format == 'capnp':
        with open(args.output, 'wb') as f:
            write_capnp_file(message, f)
    elif args.input_format == 'json':
        json_data = fpga_interchange.converters.to_yaml(message)
        with open(args.output, 'w') as f:
            json.dump(json_data, f)
    elif args.input_format == 'yaml':
        yaml_data = fpga_interchange.converters.to_yaml(message)
        yaml_string = yaml.dump(yaml_data, Dumper=Dumper)
        with open(args.output, 'w') as f:
            f.write(yaml_string)
    else:
        assert False, 'Invalid output format {}'.format(args.output_format)

if __name__ == "__main__":
    main()
