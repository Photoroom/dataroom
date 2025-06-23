migration = {
    "source": {
        "index": "images2",
    },
    "dest": {"index": "images"},
    "script": {
        "lang": "painless",
        "source": """
            // Rename attr_.*_integer to attr_.*_long
            
            // collect all keys that need to be modified
            ArrayList keysToModify = new ArrayList();
            for (entry in ctx._source.entrySet()) {
                String key = entry.getKey();
                if (key.startsWith("attr_") && key.endsWith("_integer")) {
                    keysToModify.add(key);
                }
            }
            
            // then perform the modifications
            for (String key : keysToModify) {
                String newKey = key.substring(0, key.length() - "_integer".length()) + "_long";
                ctx._source.put(newKey, ctx._source.get(key));
                ctx._source.remove(key);
            }
        """,
    },
}
