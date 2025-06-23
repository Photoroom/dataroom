
export default function defaultValue(value: any, defaultValue: any = '<empty>', emptyValues: any[] = [undefined, null, '']) {
  if (emptyValues.includes(value)) {
    return defaultValue;
  }
  if (typeof value === 'boolean') {
    return '<' + String(value) + '>';
  }
  return value;
}
