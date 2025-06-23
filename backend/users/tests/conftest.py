import freezegun

# https://github.com/huggingface/transformers/issues/24545
freezegun.config.configure(extend_ignore_list=["transformers"])
