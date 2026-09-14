---
title: Large language model - Wikipedia
source_type: web
source_url: https://en.wikipedia.org/wiki/Large_language_model
published_at: '2023-03-09'
captured_at: '2026-09-15 07:12:26'
sitename: Wikimedia Foundation, Inc.
bytes: 1068483
detected_type: web
---

# Large language model - Wikipedia

> 来源：Wikimedia Foundation, Inc. · 日期 2023-03-09
> 原链接：https://en.wikipedia.org/wiki/Large_language_model

A **large language model** (**LLM**) is an [AI model](https://en.wikipedia.org/wiki/Machine_learning#Models) (typically a [neural network](https://en.wikipedia.org/wiki/Neural_network_(machine_learning))) trained on a vast amount of text for [natural language processing](https://en.wikipedia.org/wiki/Natural_language_processing) tasks, especially [language generation](https://en.wikipedia.org/wiki/Language_generation). LLMs can typically generate, summarize, translate, and analyze text in many contexts.[1] They are the basis for many modern [chatbots](https://en.wikipedia.org/wiki/Chatbot), such as [ChatGPT](https://en.wikipedia.org/wiki/ChatGPT), [Claude](https://en.wikipedia.org/wiki/Claude_(AI)), [Gemini](https://en.wikipedia.org/wiki/Google_Gemini), [Grok](https://en.wikipedia.org/wiki/Grok_(chatbot)), and [DeepSeek](https://en.wikipedia.org/wiki/DeepSeek_(chatbot)).
 
LLMs are typically based on [transformer](https://en.wikipedia.org/wiki/Transformer_(deep_learning)) architecture.[2] [Generative pre-trained transformers](https://en.wikipedia.org/wiki/Generative_pre-trained_transformer) (GPTs) are a type of LLM that is pre-trained to predict the next word.[3] GPTs are then often [fine-tuned](https://en.wikipedia.org/wiki/Fine-tuning_(deep_learning)) to follow instructions and to behave as assistants.[4]
 
Biased or inaccurate training data can make an LLM's output less reliable. [Benchmark](https://en.wikipedia.org/wiki/Language_model_benchmark) evaluations for LLMs attempt to measure [model reasoning](https://en.wikipedia.org/wiki/Reasoning_model), factual accuracy, [alignment](https://en.wikipedia.org/wiki/AI_alignment), and [safety](https://en.wikipedia.org/wiki/AI_safety).
 
## History
 
*The number of publications about large language models by year grouped by publication types*
 
*The [training](https://en.wikipedia.org/wiki/AI_training) [compute](https://en.wikipedia.org/wiki/Compute_(machine_learning)) of notable large models in FLOPs vs publication date over the period 2010–2024. For overall notable models (top left), frontier models (top right), top language models (bottom left) and top models within leading companies (bottom right). The majority of these models are language models.*
 
*The training compute of notable large AI models in FLOPs vs publication date over the period 2017–2024. The majority of large models are language models or multimodal models with language capacity.*
 
Before the emergence of [transformer](https://en.wikipedia.org/wiki/Transformer_(deep_learning))-based models in 2017, some [language models](https://en.wikipedia.org/wiki/Language_model) were considered large relative to the computational and data constraints of their time. In the early 1990s, [IBM](https://en.wikipedia.org/wiki/IBM)'s [statistical models](https://en.wikipedia.org/wiki/Statistical_model) pioneered [word alignment](https://en.wikipedia.org/wiki/Bitext_word_alignment) techniques for machine translation, laying the groundwork for [corpus-based language modeling](https://en.wikipedia.org/wiki/Construction_grammar). In 2001, a smoothed [*n*-gram model](https://en.wikipedia.org/wiki/Word_n-gram_language_model), such as those employing [Kneser–Ney smoothing](https://en.wikipedia.org/wiki/Kneser–Ney_smoothing), trained on 300 million words, achieved state-of-the-art [perplexity](https://en.wikipedia.org/wiki/Perplexity) on benchmark tests.[5] During the 2000s, with the rise of widespread [internet access](https://en.wikipedia.org/wiki/Internet_access), researchers began compiling massive text datasets from the web ("web as corpus"[6]) to train statistical language models.[7][8]

Moving beyond *n*-gram models, researchers started in 2000 to use neural networks as language models.[9] Following the breakthrough of [deep neural networks](https://en.wikipedia.org/wiki/Deep_learning) in [image classification](https://en.wikipedia.org/wiki/Computer_vision) around 2012,[10] similar architectures were adapted for language tasks. This shift was marked by the development of [word embeddings](https://en.wikipedia.org/wiki/Word_embedding) (e.g., [Word2Vec](https://en.wikipedia.org/wiki/Word2vec) by [Mikolov](https://en.wikipedia.org/wiki/Tomáš_Mikolov) in 2013) and sequence-to-sequence ([seq2seq](https://en.wikipedia.org/wiki/Seq2seq)) models using [LSTM](https://en.wikipedia.org/wiki/Long_short-term_memory). In 2016, Google transitioned its translation service to [neural machine translation](https://en.wikipedia.org/wiki/Neural_machine_translation) (NMT), replacing statistical phrase-based models with deep [recurrent neural networks](https://en.wikipedia.org/wiki/Recurrent_neural_network). These early NMT systems used LSTM-based [encoder-decoder architectures](https://en.wikipedia.org/wiki/Encoder-decoder_model), as they preceded the invention of [transformers](https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)).

*An illustration of the main components of the transformer model from the original paper, where layers were normalized after (instead of before) multiheaded attention*
 
At the 2017 [NeurIPS](https://en.wikipedia.org/wiki/NeurIPS) conference, [Google](https://en.wikipedia.org/wiki/Google) researchers introduced the transformer architecture in their landmark paper "[Attention Is All You Need](https://en.wikipedia.org/wiki/Attention_Is_All_You_Need)".[11] This paper's goal was to improve upon 2014 seq2seq technology, and was based mainly on the [attention](https://en.wikipedia.org/wiki/Attention_(machine_learning)) mechanism developed by Bahdanau et al. in 2014.[12][13] The following year in 2018, [BERT](https://en.wikipedia.org/wiki/BERT_(language_model)) was introduced and quickly became "ubiquitous".[14] Though the original transformer has both encoder and decoder blocks, BERT is an encoder-only model. Academic and research usage of BERT began to decline in 2023, following rapid improvements in the abilities of decoder-only models (such as GPT) to solve tasks via [prompting](https://en.wikipedia.org/wiki/Prompt_engineering).[15]
 
Although decoder-only [GPT-1](https://en.wikipedia.org/wiki/GPT-1) was introduced in 2018, it was [GPT-2](https://en.wikipedia.org/wiki/GPT-2) in 2019 that caught widespread attention because [OpenAI](https://en.wikipedia.org/wiki/OpenAI) claimed to have initially deemed it too powerful to release publicly, out of fear of malicious use.[16] [GPT-3](https://en.wikipedia.org/wiki/GPT-3) in 2020 went a step further and as of 2025 is available only via [API](https://en.wikipedia.org/wiki/Web_API) with no offering of downloading the model to execute locally. But it was the consumer-facing chatbot [ChatGPT](https://en.wikipedia.org/wiki/ChatGPT) in late 2022 that received extensive media coverage and public attention by 2023.[17] The 2023 [GPT-4](https://en.wikipedia.org/wiki/GPT-4) was praised for its increased accuracy and as a "holy grail" for its [multimodal](https://en.wikipedia.org/wiki/Multimodal_learning) capabilities.[18] OpenAI did not reveal the high-level architecture and the number of [parameters](https://en.wikipedia.org/wiki/Parameter#Artificial_intelligence) of GPT-4. The release of ChatGPT led to an uptick in LLM usage across several research subfields of computer science, including robotics, software engineering, and societal impact work.[15] In 2024, OpenAI released the [reasoning model](https://en.wikipedia.org/wiki/Reasoning_language_model) [OpenAI o1](https://en.wikipedia.org/wiki/OpenAI_o1), which generates long chains of thought before returning a final answer.[19] Many LLMs with parameter counts comparable to those of OpenAI's GPT series have been developed.[20]
 
Since 2022, [open-source](https://en.wikipedia.org/wiki/Open-source_artificial_intelligence) models (those with their source code and weights made publicly available) have been gaining popularity, especially at first with [BLOOM](https://en.wikipedia.org/wiki/BLOOM_(language_model)) and [LLaMA](https://en.wikipedia.org/wiki/LLaMA), though both have restrictions on the field of use. [Mistral AI](https://en.wikipedia.org/wiki/Mistral_AI)'s open-weight models Mistral 7B and Mixtral 8x7B have a more permissive [Apache License](https://en.wikipedia.org/wiki/Apache_License). In January 2025, [DeepSeek](https://en.wikipedia.org/wiki/DeepSeek) released DeepSeek R1, a 671-billion-parameter open-weight model that performs comparably to OpenAI o1 but at a much lower price per token for users.[21]
 
Since 2023, many LLMs have been trained to be [multimodal](https://en.wikipedia.org/wiki/Multimodal_learning), having the ability to also process or generate other types of data, such as images, audio, or 3D meshes.
 
Open-weight LLMs have become more influential since 2023. Per Vake et al. (2025), community-driven contributions to open-weight models improve their efficiency and performance via collaborative platforms such as [Hugging Face](https://en.wikipedia.org/wiki/Hugging_Face).[22]
 
## Dataset preprocessing
 
### Tokenization
 
As [machine learning](https://en.wikipedia.org/wiki/Machine_learning) algorithms process numbers rather than text, the text must be converted to numbers. In the first step, a vocabulary is decided upon, then integer indices are arbitrarily but uniquely assigned to each vocabulary entry, and finally, an [embedding](https://en.wikipedia.org/wiki/Word_embedding) is associated with the integer index. Algorithms include [byte-pair encoding](https://en.wikipedia.org/wiki/Byte-pair_encoding) (BPE) and WordPiece. There are also special tokens serving as [control characters](https://en.wikipedia.org/wiki/Control_character), such as `[MASK]` for masked-out token (as used in [BERT](https://en.wikipedia.org/wiki/BERT_(language_model))), and `[UNK]` ("unknown") for characters not appearing in the vocabulary. Also, some special symbols are used to denote special text formatting. For example, "Ġ" denotes a preceding whitespace in [RoBERTa](https://en.wikipedia.org/wiki/RoBERTa) and GPT and "##" denotes continuation of a preceding word in BERT.[23]
 
For example, the BPE tokenizer used by the legacy version of [GPT-3](https://en.wikipedia.org/wiki/GPT-3) would split `tokenizer: texts -> series of numerical "tokens"` as
 
| token | izer | : | texts | -> | series | of | numerical | " | t | ok | ens | " |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
 
Tokenization also [compresses](https://en.wikipedia.org/wiki/Data_compression) the datasets. Because LLMs generally require input to be an [array](https://en.wikipedia.org/wiki/Array_(data_structure)) that is not [jagged](https://en.wikipedia.org/wiki/Jagged_array), the shorter texts must be "padded" until they match the length of the longest one.
 
#### Byte-pair encoding
 
As an example, consider a tokenizer based on byte-pair encoding. In the first step, all unique characters (including blanks and [punctuation marks](https://en.wikipedia.org/wiki/Punctuation_mark)) are treated as an initial set of [*n*-grams](https://en.wikipedia.org/wiki/N-gram) (i.e. initial set of uni-grams). Successively the most frequent pair of adjacent characters is merged into a bi-gram and all instances of the pair are replaced by it. All occurrences of adjacent pairs of (previously merged) *n*-grams that most frequently occur together are then again merged into even lengthier *n*-gram, until a vocabulary of prescribed size is obtained. After a tokenizer is trained, any text can be tokenized by it, as long as it does not contain characters not appearing in the initial-set of uni-grams.[24]
 
### Dataset cleaning
 
In the context of training LLMs, datasets are typically cleaned by removing low-quality, duplicated, or toxic data.[25] Cleaned datasets can increase training efficiency and lead to improved downstream performance.[26] A trained LLM can be used to clean datasets for training a further LLM.[27]
 
With the increasing proportion of LLM-generated content on the web, data cleaning in the future may include filtering out such content. LLM-generated content can pose a problem if the content is similar to human text (making filtering difficult) but of lower quality (degrading performance of models trained on it).[1]
 
### Synthetic data
 
Training of largest language models might need more linguistic data than naturally available, or that the naturally occurring data is of insufficient quality. In these cases, synthetic data might be used.
 
## Training
 
An LLM is a type of [foundation model](https://en.wikipedia.org/wiki/Foundation_model) (large X model) trained on language. LLMs can be trained in different ways. In particular, GPT models are first pretrained to predict the next word on a large amount of data, before being fine-tuned.[3]
 
### Cost
 
Substantial infrastructure is necessary for training the largest models. The tendency towards larger models is visible in the [list of large language models](https://en.wikipedia.org/wiki/List_of_large_language_models). For example, the training of GPT-2 (i.e. a 1.5-billion-parameter model) in 2019 cost $50,000, while training of the [PaLM](https://en.wikipedia.org/wiki/PaLM) (i.e. a 540-billion-parameter model) in 2022 cost $8 million, and Megatron-Turing NLG 530B (in 2021) cost around $11 million. The qualifier "large" in "large language model" is inherently vague, as there is no definitive threshold for the number of parameters required to qualify as "large".
 
### Fine-tuning
 
Before being [fine-tuned](https://en.wikipedia.org/wiki/Fine-tuning_(deep_learning)), most LLMs are next-token predictors.[28] The fine-tuning shapes the LLM's behavior via techniques like [reinforcement learning from human feedback](https://en.wikipedia.org/wiki/Reinforcement_learning_from_human_feedback) (RLHF) or [constitutional AI](https://en.wikipedia.org/wiki/Constitutional_AI).[29]
 
Instruction fine-tuning is a form of [supervised learning](https://en.wikipedia.org/wiki/Supervised_learning) used to teach LLMs to follow user instructions. In 2022, OpenAI demonstrated [InstructGPT](https://en.wikipedia.org/wiki/InstructGPT), a version of GPT-3 similarly fine-tuned to follow instructions.[30]
 
RLHF involves training a reward model to predict which text humans prefer. Then, the LLM can be fine-tuned through [reinforcement learning](https://en.wikipedia.org/wiki/Reinforcement_learning) to better satisfy this reward model.[31]
 
## Inference
 
[Inference](https://en.wikipedia.org/wiki/Inference) is the process of providing [input](https://en.wikipedia.org/wiki/Input_(computer_science)) to a trained large language model and receiving generated [output](https://en.wikipedia.org/wiki/Input/output), such as [text](https://en.wikipedia.org/wiki/Text), [images](https://en.wikipedia.org/wiki/Image), [code](https://en.wikipedia.org/wiki/Source_code), [video](https://en.wikipedia.org/wiki/Video), and files such as [CSV](https://en.wikipedia.org/wiki/CSV_(file_format)), [JSON](https://en.wikipedia.org/wiki/JSON), [XML](https://en.wikipedia.org/wiki/XML), [PDF](https://en.wikipedia.org/wiki/PDF), and [Microsoft Word](https://en.wikipedia.org/wiki/Microsoft_Word) documents, as well as other [multimodal](https://en.wikipedia.org/wiki/Multimodal_interaction) forms. Large language models are commonly accessed through [chatbot](https://en.wikipedia.org/wiki/Chatbot) websites and applications, which may offer free or subscription-based access, [command-line interfaces](https://en.wikipedia.org/wiki/Command-line_interface) and [terminal](https://en.wikipedia.org/wiki/Terminal_emulator) user interfaces, or [extensions](https://en.wikipedia.org/wiki/Plug-in_(computing)) for [source-code editors](https://en.wikipedia.org/wiki/Source-code_editor) and [integrated development environments](https://en.wikipedia.org/wiki/Integrated_development_environment) such as [Visual Studio Code](https://en.wikipedia.org/wiki/Visual_Studio_Code), where LLMs can be accessed through built-in providers, external [APIs](https://en.wikipedia.org/wiki/API), or locally hosted models.[32][33][34]
 
### Hosted inference
 
*Top 20 large language models by token usage on [OpenRouter](https://en.wikipedia.org/wiki/OpenRouter)*
 
Hosted inference runs a language model on remote [AI data centers](https://en.wikipedia.org/wiki/AI_data_center) and makes the [output](https://en.wikipedia.org/wiki/Input/output) available to users over the [Internet](https://en.wikipedia.org/wiki/Internet). Models may be hosted by their developers or accessed through third-party [API](https://en.wikipedia.org/wiki/API) services such as [OpenRouter](https://en.wikipedia.org/wiki/OpenRouter) or [LiteLLM](https://en.wikipedia.org/wiki/LiteLLM) which are AI gateways that provide access to models from multiple developers through a common interface.[35] The service lists the price of each model, generally according to the number of input and output [tokens](https://en.wikipedia.org/wiki/Tokenization_(data_security)) processed, and routes requests among available providers.[36]
 
### Local inference
 
Some [open-weight](https://en.wikipedia.org/wiki/Open_weights) language models can be downloaded and run locally on a personal computer or server rather than accessed through a remote [API](https://en.wikipedia.org/wiki/Web_API).[37] The model files are stored on local storage, while during [inference](https://en.wikipedia.org/wiki/Inference#Inference_engines) the model weights and other data are held in system [RAM](https://en.wikipedia.org/wiki/Random-access_memory), [VRAM](https://en.wikipedia.org/wiki/Video_random-access_memory), or [unified memory](https://en.wikipedia.org/wiki/Unified_memory_architecture) for processing by a [CPU](https://en.wikipedia.org/wiki/Central_processing_unit) or [GPU](https://en.wikipedia.org/wiki/Graphics_processing_unit). Models can also be divided between system and GPU memory when insufficient VRAM is available.[38]
 
The amount of memory and power required depends largely on the model's number of parameters and the numerical precision used to store them. [Quantization](https://en.wikipedia.org/wiki/Quantization_(signal_processing)#Machine_learning) can reduce the size of a model by storing its weights at lower precision, allowing larger models to run on consumer hardware with less memory.[39]
 
#### Locally hosted software
 
Software used for locally hosted or self-hosted language-model inference includes:
 
- llama.cpp — C and C++ inference software designed to run language models on a wide range of CPUs and GPUs.[40]
- LM Studio — desktop software for downloading and running local models using runtimes including llama.cpp and MLX.[41][42]
- MLX — Apple's machine learning framework, the MLX LM package runs and fine-tunes language models on Apple silicon.[43]
- Ollama — software for downloading and running language models locally on personal computers.[37]
- Open WebUI — self-hosted web interface for locally running LLMs.[44]
- vLLM — high-throughput inference and model-serving software designed primarily for GPU-accelerated systems.[45]
 
## Architecture
 
LLMs are generally based on the [transformer](https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)) architecture, which leverages an [attention](https://en.wikipedia.org/wiki/Attention_(machine_learning)) mechanism that enables the model to process relationships between all elements in a sequence simultaneously, regardless of their distance from each other.[11][46] Peng et al. (2023) proposed [state-space representation](https://en.wikipedia.org/wiki/State-space_representation) models as an alternative.[47]
 
### Attention mechanism and context window
 
*When each head calculates, according to its own criteria, how much other tokens are relevant for the "it_" token, note that the second attention head, represented by the second column, is focusing most on the first two rows, i.e. the tokens "The" and "animal", while the third column is focusing most on the bottom two rows, i.e. on "tired", which has been tokenized into two tokens.[48]*
 
In order to find out which tokens are relevant to each other within the scope of the [context window](https://en.wikipedia.org/wiki/Context_window), the attention mechanism calculates "soft" weights for each token, more precisely for its embedding, by using multiple attention heads, each with its own "relevance" for calculating its own soft weights. For example, the small (i.e. 117M parameter sized) [GPT-2](https://en.wikipedia.org/wiki/GPT-2) model has had twelve attention heads and a context window of only 1k tokens.[49]
 
*Autoregressive* models, such as [GPTs](https://en.wikipedia.org/wiki/Generative_pretrained_transformer), are trained to guess how a sequence continues; for example, whether the word sequence "I like to eat" is more likely to be followed by the word "bread" or the word "rocks". [*Masked*](https://en.wikipedia.org/wiki/Cloze_test) models, such as BERT,[50] are trained to guess parts that are missing from a sequence, such as whether the missing word in "I like to ___ roses" is more likely to be the word "smell" or the word "eat". The model's predictions are based on the properties of sequences within its training dataset.[51]
 
### Mixture of experts
 
A [mixture of experts](https://en.wikipedia.org/wiki/Mixture_of_experts) (MoE) is a [machine learning](https://en.wikipedia.org/wiki/Machine_learning) architecture in which multiple specialized neural networks ("experts") work together, with a gating mechanism that routes each input to the most appropriate expert(s). Mixtures of experts can reduce inference costs, as only a fraction of the parameters are used for each input.[52]
 
### Parameter size
 
Typically, LLMs are trained with single or half-precision [floating point numbers](https://en.wikipedia.org/wiki/Floating_point_numbers) (float32 and float16). One float16 has 16 bits, or 2 bytes, and so one billion parameters require 2 gigabytes. The largest models typically have more than 100 billion parameters, which places them outside the range of most consumer electronics.[53]
 
In 2021, [Google Brain](https://en.wikipedia.org/wiki/Google_Brain) released Switch Transformer, one of the first [natural language processing](https://en.wikipedia.org/wiki/Natural_language_processing) (NLP) models to cross one trillion parameters.[54] As of July 2026, the largest [open weight](https://en.wikipedia.org/wiki/Open_weights) [frontier model](https://en.wikipedia.org/wiki/Foundation_model#Frontier_models) is [Kimi K3](https://en.wikipedia.org/wiki/Kimi_(AI)), developed by [Moonshot AI](https://en.wikipedia.org/wiki/Moonshot_AI), at 2.8 trillion parameters.[55] According to industry estimates reported by the *[Financial Times](https://en.wikipedia.org/wiki/Financial_Times)*, [Anthropic](https://en.wikipedia.org/wiki/Anthropic)'s [Claude Mythos](https://en.wikipedia.org/wiki/Claude_Mythos), its most powerful model, restricted from public access, has approximately 8 trillion parameters, while its public 'Mythos-class' model Fable 5 has approximately 5 trillion parameters.[56][57][58]
 
#### Quantization
 
*Post-training [quantization](https://en.wikipedia.org/wiki/Quantization_(signal_processing))*[59] aims to decrease the space requirement by lowering precision of the parameters of a trained model, while preserving most of its performance. Quantization can be further classified as *static quantization* if the quantization parameters are determined beforehand (typically during a calibration phase), and *dynamic quantization* if the quantization is applied during inference. The simplest form of quantization simply truncates all the parameters to a given number of bits: this is applicable to static as well as dynamic quantization, but loses much precision. Dynamic quantization allows for the use of a different quantization [codebook](https://en.wikipedia.org/wiki/Codebook#Data_compression) per layer, either a lookup table of values or a linear mapping (scaling factor and bias), at the cost of foregoing the possible speed improvements from using lower-precision arithmetic.
 
It is possible to fine-tune quantized models using [low-rank adaptation](https://en.wikipedia.org/wiki/LoRA).[60]
 
## Extensibility
 
Beyond basic text generation, various techniques have been developed to extend LLM capabilities, including the use of external tools and data sources, improved reasoning on complex problems, and enhanced instruction-following or autonomy through prompting methods.
 
### Prompt engineering
 
In 2020, [OpenAI](https://en.wikipedia.org/wiki/OpenAI) researchers demonstrated that their new model [GPT-3](https://en.wikipedia.org/wiki/GPT-3) could understand what format to use given a few rounds of Q and A (or other type of task) in the input data as example, thanks in part due to the RLHF technique. This technique, called *few-shot prompting*, allows LLMs to be adapted to any task without requiring fine-tuning.[1] Also in 2022, it was found that the base GPT-3 model can generate an instruction based on user input. The generated instruction along with user input is then used as input to another instance of the model under a "Instruction: [...], Input: [...], Output:" format. The other instance is able to complete the output and often produces the correct answer in doing so. The ability to "self-instruct" makes LLMs able to [bootstrap](https://en.wikipedia.org/wiki/Bootstrapping) themselves toward a correct answer.[61]
 
### Dialogue processing (chatbot)
 
An LLM can be turned into a [chatbot](https://en.wikipedia.org/wiki/Chatbot) by specializing it for conversation. User input is prefixed with a marker such as "Q:" or "User:" and the LLM is asked to predict the output after a fixed "A:" or "Assistant:". This type of model became commercially available in 2022 with ChatGPT, a sibling model of InstructGPT fine-tuned to accept and produce dialog-formatted text based on GPT-3.5. It could similarly follow user instructions. Before the stream of User and Assistant lines, a chat context usually starts with a few lines of overarching instructions, from a role called "developer" or "system" to convey a higher authority than the user's input. This is called a "system prompt".
 
### Retrieval-augmented generation
 
[Retrieval-augmented generation](https://en.wikipedia.org/wiki/Retrieval-augmented_generation) (RAG) is an approach that integrates LLMs with [document retrieval](https://en.wikipedia.org/wiki/Document_retrieval) systems. Given a query, a document retriever is called to retrieve the most relevant documents. This is usually done by encoding the query and the documents into vectors, then finding the documents with vectors (usually stored in a [vector database](https://en.wikipedia.org/wiki/Vector_database)) most similar to the vector of the query. The LLM then generates an output based on both the query and context included from the retrieved documents.[62]
 
### Tool use
 
Tool use is a mechanism that enables LLMs to interact with external systems, applications, or data sources. It can allow LLMs to, for example, fetch real-time information from an API or to execute code. A program separate from the LLM watches the output stream of the LLM for a special tool-calling syntax. When these special tokens appear, the program calls the tool accordingly and feeds its output back into the LLM's input stream.[63]
 
Early tool-using LLMs were fine-tuned on the use of specific tools. But fine-tuning LLMs for the ability to read [API](https://en.wikipedia.org/wiki/API) documentation and call APIs correctly has greatly expanded the range of tools accessible to an LLM.[64][65]
 
### Agency
 
An LLM is typically not an [autonomous agent](https://en.wikipedia.org/wiki/Autonomous_agent) by itself, as it lacks the ability to interact with dynamic environments, recall past behaviors, and plan future actions. But it can be transformed into an agent by adding supporting elements: the role (profile) and the surrounding environment of an agent can be additional inputs to the LLM, while memory can be integrated as a tool or provided as additional input. Instructions and input patterns are used to make the LLM plan actions and tool use is used to potentially carry out these actions.[66]
 
In the DEPS ("describe, explain, plan and select") method, an LLM is first connected to the visual world via image descriptions. It is then prompted to produce plans for complex tasks and behaviors based on its pretrained knowledge and the environmental feedback it receives.[67]
 
The *Reflexion method* constructs an agent that learns over multiple episodes. At the end of each episode, the LLM is given the record of the episode, and prompted to think up "lessons learned", which would help it perform better at a subsequent episode. These "lessons learned" are stored as a form of long-term memory and given to the agent in the subsequent episodes.[68]
 
[Monte Carlo tree search](https://en.wikipedia.org/wiki/Monte_Carlo_tree_search) can use an LLM as rollout heuristic. When a programmatic [world model](https://en.wikipedia.org/wiki/World_model_(artificial_intelligence)) is not available, an LLM can also be prompted with a description of the environment to act as world model.[69]
 
Multiple agents with memory can interact socially.[70]
 
#### Chaining
 
*Prompt chaining* was introduced in 2022.[71] In this method, a user manually breaks a complex problem down into several steps. In each step, the LLM receives as input a prompt telling it what to do and some results from preceding steps. The result from one step is then reused in a next step, until a final answer is reached. The ability of an LLM to follow instructions means that even non-experts can write a successful collection of stepwise prompts given a few rounds of trial and error.[72][73]
 
A 2022 paper demonstrated a separate technique called *[chain-of-thought prompting](https://en.wikipedia.org/wiki/Chain-of-thought_prompting)*, which makes the LLM break the question down autonomously. An LLM is given some examples where the "assistant" verbally breaks down the thought process before arriving at an answer. The LLM mimics these examples and also tries to spend some time generating intermediate steps before providing the final answer. This additional step elicited by prompting improves the correctness of the LLM on relatively complex questions. On math word questions, a prompted model can exceed even fine-tuned GPT-3 with a verifier.[74][75] Chain-of-thought can also be elicited by simply adding an instruction like "Let's think step by step" to the prompt, in order to encourage the LLM to proceed methodically instead of trying to directly guess the answer.[76]
 
#### Model-native reasoning
 
In late 2024, a new approach to LLM development emerged with "reasoning models".[77] These are trained to generate step-by-step analysis before producing final answers, enabling better results on complex tasks, for instance in mathematics, coding and logic.[78] OpenAI introduced this concept with their [o1](https://en.wikipedia.org/wiki/OpenAI_o1) model in September 2024, followed by [o3](https://en.wikipedia.org/wiki/OpenAI_o3) in April 2025. On the [International Mathematics Olympiad](https://en.wikipedia.org/wiki/International_Mathematical_Olympiad) qualifying exam problems, [GPT-4o](https://en.wikipedia.org/wiki/GPT-4o) achieved 13% accuracy while o1 reached 83%.[79]
 
In January 2025, the Chinese company [DeepSeek](https://en.wikipedia.org/wiki/DeepSeek) released DeepSeek-R1, a 671-billion-parameter open-weight reasoning model that achieved comparable performance to OpenAI's o1 while being significantly more cost-effective to operate. Unlike proprietary models from OpenAI, DeepSeek-R1's open-weight nature allowed researchers to study and build upon the algorithm, though its training data remained private.[80]
 
These reasoning models typically require more computational resources per query compared to traditional LLMs, as they perform more extensive processing to work through problems step by step.[79]
 
## Forms of input and output
 
### Multimodality
 
Multimodality means having multiple modalities, where a "[modality](https://en.wikipedia.org/wiki/Modality_(human–computer_interaction))" refers to a type of input or output, such as video, image, audio, text, [proprioception](https://en.wikipedia.org/wiki/Proprioception), etc.[81] For example, [Google PaLM](https://en.wikipedia.org/wiki/Pathways_Language_Model) model was fine-tuned into a multimodal model and applied to [robotic control](https://en.wikipedia.org/wiki/Robot_control).[82] [LLaMA](https://en.wikipedia.org/wiki/LLaMA) models have also been turned multimodal using the tokenization method, to allow image inputs,[83] and video inputs.[84] [GPT-4o](https://en.wikipedia.org/wiki/GPT-4o) can process and generate text, audio and images.[85]
 
A common method to create multimodal models out of an LLM is to "tokenize" the output of a trained encoder. Concretely, one can construct an LLM that can understand images as follows: take a trained LLM, and take a trained image encoder E {\displaystyle E} ![{\displaystyle E}](https://wikimedia.org/api/rest_v1/media/math/render/svg/4232c9de2ee3eec0a9c0a19b15ab92daa6223f9b). Make a small [multilayer perceptron](https://en.wikipedia.org/wiki/Multilayer_perceptron) f {\displaystyle f} ![{\displaystyle f}](https://wikimedia.org/api/rest_v1/media/math/render/svg/132e57acb643253e7810ee9702d9581f159a1c61), so that for any image y {\displaystyle y} ![{\displaystyle y}](https://wikimedia.org/api/rest_v1/media/math/render/svg/b8a6208ec717213d4317e666f1ae872e00620a0d), the post-processed vector f ( E ( y ) ) {\displaystyle f(E(y))} ![{\displaystyle f(E(y))}](https://wikimedia.org/api/rest_v1/media/math/render/svg/8d41d0ec0611a795f65ea14a43b8016462703a8e) has the same dimensions as an encoded token. That is an "image token". Then, one can interleave text tokens and image tokens. The compound model is then fine-tuned on an image-text dataset. This basic construction can be applied with more sophistication to improve the model. The image encoder may be [frozen](https://en.wikipedia.org/wiki/Hang_(computing)) to improve stability.[86] This type of method, where embeddings from multiple modalities are fused and the predictor is trained on the combined embeddings, is called *early fusion*.
 
Another method, called *intermediate fusion*, involves each modality being first processed independently to obtain modality-specific representations; then these intermediate representations are fused together.[87] In general, cross-attention is used for integrating information from different modalities. As an example, the Flamingo model uses cross-attention layers to inject visual information into its pre-trained language model.[88]
 
### Non-natural languages
 
LLMs can handle [programming languages](https://en.wikipedia.org/wiki/Programming_language) similarly to how they handle natural languages. No special change in token handling is needed as code, like human language, is represented as plain text. LLMs can generate code from problem statements or instructions written in [natural language](https://en.wikipedia.org/wiki/Natural_language), a process sometimes called [vibe coding](https://en.wikipedia.org/wiki/Vibe_coding). They can also describe code in natural language or translate it into other programming languages. They were originally used as a [code completion](https://en.wikipedia.org/wiki/Code_completion) tool, but advances have moved them towards [automatic programming](https://en.wikipedia.org/wiki/Automatic_programming). Services such as [GitHub Copilot](https://en.wikipedia.org/wiki/GitHub_Copilot) offer LLMs specifically trained, fine-tuned, or prompted for programming.[89][90]
 
In [computational biology](https://en.wikipedia.org/wiki/Computational_biology), transformer-based architectures, such as DNA LLMs, have also proven useful in analyzing biological sequences: [protein](https://en.wikipedia.org/wiki/Protein), [DNA](https://en.wikipedia.org/wiki/DNA), and [RNA](https://en.wikipedia.org/wiki/RNA). With proteins they appear able to capture a degree of "grammar" from the amino-acid sequence, by mapping that sequence into an [embedding](https://en.wikipedia.org/wiki/Embedding_(machine_learning)). On tasks such as [structure prediction](https://en.wikipedia.org/wiki/Protein_structure_prediction) and [mutational](https://en.wikipedia.org/wiki/Mutation) outcome prediction, a small model using an embedding as input can approach or exceed much larger models using [multiple sequence alignments](https://en.wikipedia.org/wiki/Multiple_sequence_alignment) (MSA) as input.[91] ESMFold, [Meta Platforms](https://en.wikipedia.org/wiki/Meta_Platforms)' embedding-based method for protein structure prediction, runs an order of magnitude faster than [AlphaFold2](https://en.wikipedia.org/wiki/AlphaFold2) thanks to the removal of an MSA requirement and a lower parameter count due to the use of embeddings.[92] Meta hosts ESM Atlas, a database of 772 million structures of [metagenomic](https://en.wikipedia.org/wiki/Metagenomic) proteins predicted using ESMFold.[93] An LLM can also design proteins unlike any seen in nature.[94] Nucleic acid models have proven useful in detecting [regulatory sequences](https://en.wikipedia.org/wiki/Regulatory_sequence),[95] sequence classification, RNA-RNA interaction prediction, and RNA structure prediction.[96]
 
## Properties
 
### Scaling laws
 
The performance of an LLM after pretraining largely depends on the:
 
- C {\displaystyle C} : cost of pretraining (the total amount of compute used),
- N {\displaystyle N} : size of the artificial neural network itself, such as number of parameters (i.e. amount of neurons in its layers, amount of weights between them and biases),
- D {\displaystyle D} : size of its pretraining dataset (i.e. number of tokens in corpus).
 
*Scaling laws* are [empirical statistical laws](https://en.wikipedia.org/wiki/Empirical_statistical_laws) that predict LLM performance based on such factors. One particular scaling law ("[Chinchilla scaling](https://en.wikipedia.org/wiki/Chinchilla_AI)") for LLM autoregressively trained for one epoch, with a [log-log](https://en.wikipedia.org/wiki/Log-log_plot) [learning rate](https://en.wikipedia.org/wiki/Learning_rate) schedule, states that:[97] { C = C 0 N D L = A N α α + B D β β + L 0 {\displaystyle {\begin{cases}C=C_{0}ND\\[6pt]L={\frac {A}{N^{\alpha }}}+{\frac {B}{D^{\beta }}}+L_{0}\end{cases}}} ![{\displaystyle {\begin{cases}C=C_{0}ND\\[6pt]L={\frac {A}{N^{\alpha }}}+{\frac {B}{D^{\beta }}}+L_{0}\end{cases}}}](https://wikimedia.org/api/rest_v1/media/math/render/svg/39435f4ecd5e00c0714a4f7f71cc0b91f5973cdd) where the variables are
 
- C {\displaystyle C} is the cost of training the model, in FLOPs.
- N {\displaystyle N} is the number of parameters in the model.
- D {\displaystyle D} is the number of tokens in the training set.
- L {\displaystyle L} is the average negative log-likelihood loss per token (nats/token), achieved by the trained LLM on the test dataset.
 
and the statistical hyper-parameters are
 
- C 0 = 6 {\displaystyle C_{0}=6} , meaning that it costs 6 FLOPs per parameter to train on one token. Note that training cost is much higher than inference cost, where it costs 1 to 2 FLOPs per parameter to infer on one token.
- α α = 0.34 , β β = 0.28 , A = 406.4 , B = 410.7 , L 0 = 1.69 {\displaystyle \alpha =0.34,\beta =0.28,A=406.4,B=410.7,L_{0}=1.69}
 
### Emergent abilities
 
*At point(s) referred to as [breaks](https://en.wikipedia.org/wiki/Broken_Neural_Scaling_Law),[98] the lines change their slopes, appearing on a linear-log plot as a series of linear segments connected by arcs.*
 
Performance of bigger models on various tasks, when plotted on a log-log scale, appears as a [linear extrapolation](https://en.wikipedia.org/wiki/Linear_extrapolation) of performance achieved by smaller models. However, this linearity may be punctuated by "[break(s)](https://en.wikipedia.org/wiki/Broken_Neural_Scaling_Law)"[98] in the scaling law, where the slope of the line changes abruptly, and where larger models acquire "emergent abilities".[99] They arise from the complex interaction of the model's components and are not explicitly programmed or designed.[100]
 
Proposed examples of emergent abilities include:[99]
 
- reported arithmetics
- decoding the International Phonetic Alphabet
- unscrambling a word's letters
- disambiguating word-in-context datasets[101]
- converting spatial words
- cardinal directions (for example, replying "northeast" in response to a 3x3 grid of 8 zeros and a 1 in the top-right), color terms represented in text.[102]
- chain-of-thought prompting: In a 2022 research paper, chain-of-thought prompting only improved the performance for models that had at least 62B parameters. Smaller models perform better when prompted to answer immediately, without chain of thought.[103]
- identifying offensive content in paragraphs of Hinglish (a combination of Hindi and English), and generating a similar English equivalent of Kiswahili proverbs.[104]
 
Schaeffer *et al.* argue that the emergent abilities are not unpredictably acquired, but predictably acquired according to a [smooth scaling law](https://en.wikipedia.org/wiki/Neural_scaling_law). The authors considered a toy statistical model of an LLM solving multiple-choice questions, and showed that this statistical model, modified to account for other types of tasks, applies to these tasks as well.[105]
 
Let x {\displaystyle x} ![{\displaystyle x}](https://wikimedia.org/api/rest_v1/media/math/render/svg/87f9e315fd7e2ba406057a97300593c4802b53e4) be the number of parameter count, and y {\displaystyle y} ![{\displaystyle y}](https://wikimedia.org/api/rest_v1/media/math/render/svg/b8a6208ec717213d4317e666f1ae872e00620a0d) be the performance of the model.
 
- When y = average Pr ( correct token ) {\displaystyle y={\text{average }}\Pr({\text{correct token}})} , then ( log ⁡ ⁡ x , y ) {\displaystyle (\log x,y)} is an exponential curve (before it hits the plateau at one), which looks like emergence.
- When y = average log ⁡ ⁡ ( Pr ( correct token ) ) {\displaystyle y={\text{average }}\log(\Pr({\text{correct token}}))} , then the ( log ⁡ ⁡ x , y ) {\displaystyle (\log x,y)} plot is a straight line (before it hits the plateau at zero), which does not look like emergence.
- When y = average Pr ( the most likely token is correct ) {\displaystyle y={\text{average }}\Pr({\text{the most likely token is correct}})} , then ( log ⁡ ⁡ x , y ) {\displaystyle (\log x,y)} is a step-function, which looks like emergence.
 
## Interpretation
 
### Mechanistic interpretability
 
Large language models are typically regarded as [black boxes](https://en.wikipedia.org/wiki/Black_box), and it is not clear how they perform linguistic tasks. Similarly, it is unclear if or how LLMs should be viewed as models of the human brain and/or human mind.[106] Mechanistic interpretability is a subfield of research that aims to understand neural networks' internal workings by analyzing their concrete structures, algorithms and circuits, similar to the [reverse engineering](https://en.wikipedia.org/wiki/Reverse_engineering) of traditional software.
 
The reverse-engineering may lead to the discovery of algorithms that approximate inferences performed by an LLM. For instance, the authors trained small transformers on [modular arithmetic addition](https://en.wikipedia.org/wiki/Modular_arithmetic). The resulting models were reverse-engineered, and it turned out they used [discrete Fourier transform](https://en.wikipedia.org/wiki/Discrete_Fourier_transform).[107] The training of the model also highlighted a phenomenon called [grokking](https://en.wikipedia.org/wiki/Grokking_(machine_learning)), in which the model initially memorizes the training set ([overfitting](https://en.wikipedia.org/wiki/Overfitting)), and later suddenly learns to actually perform the calculation.[108]
 
### Understanding and intelligence
 
NLP researchers were evenly split when asked, in a 2022 survey, whether (untuned) LLMs "could (ever) understand natural language in some nontrivial sense".[109] Proponents of "LLM understanding" believe that some LLM abilities, such as mathematical reasoning, imply an ability to ["understand"](https://en.wikipedia.org/wiki/Natural_language_understanding) certain concepts. A Microsoft team argued in 2023 that GPT-4 "can solve novel and difficult tasks that span mathematics, coding, vision, medicine, law, psychology and more" and that GPT-4 "could reasonably be viewed as an early (yet still incomplete) version of an [artificial general intelligence](https://en.wikipedia.org/wiki/Artificial_general_intelligence) system": "Can one reasonably say that a system that passes exams for software engineering candidates is not *really* intelligent?"[110][111] [Ilya Sutskever](https://en.wikipedia.org/wiki/Ilya_Sutskever) argues that predicting the next word sometimes involves reasoning and deep insights, for example if the LLM has to predict the name of the criminal in an unknown detective novel after processing the entire story leading up to the revelation.[112] Some researchers characterize LLMs as "alien intelligence".[113][114] For example, Conjecture CEO [Connor Leahy](https://en.wikipedia.org/wiki/Connor_Leahy) considers untuned LLMs to be like inscrutable alien "[Shoggoths](https://en.wikipedia.org/wiki/Shoggoth)", and believes that RLHF tuning creates a "smiling facade" obscuring the inner workings of the LLM: "If you don't push it too far, the smiley face stays on. But then you give it [an unexpected] prompt, and suddenly you see this massive underbelly of insanity, of weird thought processes and clearly non-human understanding."[115][116]
 
In contrast, some skeptics of LLM understanding believe that existing LLMs are "simply remixing and recombining existing writing",[114][117] a phenomenon known as [stochastic parrot](https://en.wikipedia.org/wiki/Stochastic_parrot),[118] or they point to the deficits existing LLMs continue to have in prediction skills, reasoning skills, agency, and explainability.[109] For example, GPT-4 has natural deficits in planning and in real-time learning.[111] Generative LLMs have been observed to confidently assert claims of fact which do not seem to be [justified](https://en.wikipedia.org/wiki/Justification_(epistemology)) by their [training data](https://en.wikipedia.org/wiki/Training_data), a phenomenon which has been termed "[hallucination](https://en.wikipedia.org/wiki/Hallucination_(artificial_intelligence))".[119] Specifically, hallucinations in the context of LLMs correspond to the generation of text or responses that seem syntactically sound, fluent, and natural but are factually incorrect, nonsensical, or unfaithful to the provided source input.[120] Neuroscientist [Terrence Sejnowski](https://en.wikipedia.org/wiki/Terrence_Sejnowski) has argued that "The diverging opinions of experts on the intelligence of LLMs suggests that our old ideas based on natural intelligence are inadequate".[109]
 
Efforts to reduce or compensate for hallucinations have employed [automated reasoning](https://en.wikipedia.org/wiki/Automated_reasoning), [retrieval-augmented generation](https://en.wikipedia.org/wiki/Retrieval-augmented_generation) (RAG), [fine-tuning](https://en.wikipedia.org/wiki/Fine-tuning_(deep_learning)), and other methods.[121]
 
The matter of LLM's exhibiting intelligence or understanding has two main aspects—the first is how to model thought and language in a computer system, and the second is how to enable the computer system to generate human-like language.[109] These aspects of language as a model of [cognition](https://en.wikipedia.org/wiki/Cognition) have been developed in the field of [cognitive linguistics](https://en.wikipedia.org/wiki/Cognitive_linguistics). American linguist [George Lakoff](https://en.wikipedia.org/wiki/George_Lakoff) presented *neural theory of language* (NTL)[122] as a [computational basis](https://en.wikipedia.org/wiki/Cognitive_linguistics#Computational_approaches) for using language as a model of learning tasks and understanding. [The NTL model](https://www.icsi.berkeley.edu/icsi/projects/ai/ntl) outlines how specific neural structures of the human brain shape the nature of thought and language and in turn what are the computational properties of such neural systems that can be applied to model thought and language in a computer system. After a framework for modeling language in a computer systems was established, the focus shifted to establishing frameworks for computer systems to generate language with acceptable grammar. In his 2014 book titled *[The Language Myth: Why Language Is Not An Instinct](https://en.wikipedia.org/wiki/The_Language_Myth)*, British cognitive linguist and digital communication technologist [Vyvyan Evans](https://en.wikipedia.org/wiki/Vyvyan_Evans) mapped out the role of [probabilistic context-free grammar](https://en.wikipedia.org/wiki/Probabilistic_context-free_grammar) (PCFG) in enabling [NLP to model cognitive patterns](https://en.wikipedia.org/wiki/Natural_language_processing#Cognition) and generate human-like language.[123][124]
 
## Evaluation
 
### Perplexity
 
The canonical measure of the performance of any language model is its [perplexity](https://en.wikipedia.org/wiki/Perplexity) on a given text corpus. Perplexity measures how well a model predicts the contents of a dataset; the higher the likelihood the model assigns to the dataset, the lower the perplexity. In mathematical terms, perplexity is the exponential of the average negative log likelihood per token.
 
log ⁡ ⁡ ( Perplexity ) = − − 1 N ∑ ∑ i = 1 N log ⁡ ⁡ ( Pr ( token i ∣ ∣ context for token i ) ) {\displaystyle \log({\text{Perplexity}})=-{\frac {1}{N}}\sum _{i=1}^{N}\log(\Pr({\text{token}}_{i}\mid {\text{context for token}}_{i}))} ![{\displaystyle \log({\text{Perplexity}})=-{\frac {1}{N}}\sum _{i=1}^{N}\log(\Pr({\text{token}}_{i}\mid {\text{context for token}}_{i}))}](https://wikimedia.org/api/rest_v1/media/math/render/svg/556393708767666076b9723412bc8519284449a5)
 
Here, N {\displaystyle N} ![{\displaystyle N}](https://wikimedia.org/api/rest_v1/media/math/render/svg/f5e3890c981ae85503089652feb48b191b57aae3) is the number of tokens in the text corpus, and "context for token i {\displaystyle i} ![{\displaystyle i}](https://wikimedia.org/api/rest_v1/media/math/render/svg/add78d8608ad86e54951b8c8bd6c8d8416533d20)" depends on the specific type of LLM. If the LLM is autoregressive, then "context for token i {\displaystyle i} ![{\displaystyle i}](https://wikimedia.org/api/rest_v1/media/math/render/svg/add78d8608ad86e54951b8c8bd6c8d8416533d20)" is the segment of text appearing before token i {\displaystyle i} ![{\displaystyle i}](https://wikimedia.org/api/rest_v1/media/math/render/svg/add78d8608ad86e54951b8c8bd6c8d8416533d20). If the LLM is masked, then "context for token i {\displaystyle i} ![{\displaystyle i}](https://wikimedia.org/api/rest_v1/media/math/render/svg/add78d8608ad86e54951b8c8bd6c8d8416533d20)" is the segment of text surrounding token i {\displaystyle i} ![{\displaystyle i}](https://wikimedia.org/api/rest_v1/media/math/render/svg/add78d8608ad86e54951b8c8bd6c8d8416533d20).
 
Because language models may [overfit](https://en.wikipedia.org/wiki/Overfit) to training data, models are usually evaluated by their perplexity on a [test set](https://en.wikipedia.org/wiki/Test_set).[50] This evaluation is potentially problematic for larger models which, as they are trained on increasingly large corpora of text, are increasingly likely to inadvertently include portions of any given test set.[125]
 
#### Measures
 
In [information theory](https://en.wikipedia.org/wiki/Information_theory), the concept of [entropy](https://en.wikipedia.org/wiki/Entropy_(information_theory)) is intricately linked to perplexity, a relationship notably established by [Claude Shannon](https://en.wikipedia.org/wiki/Claude_Shannon).[126]
 
Due to their ability to accurately predict the next token, LLMs are highly capable in [lossless compression](https://en.wikipedia.org/wiki/Lossless_compression). A 2023 study by DeepMind showed that the model [Chinchilla](https://en.wikipedia.org/wiki/Chinchilla_(language_model)), despite being trained primarily on text, was able to compress [ImageNet](https://en.wikipedia.org/wiki/ImageNet) to 43% of its size, beating PNG with 58%.[127]
 
### Benchmarks
 
Benchmarks are used to evaluate LLM performance on specific tasks. Tests evaluate capabilities such as general knowledge, bias, [commonsense reasoning](https://en.wikipedia.org/wiki/Commonsense_reasoning), question answering, and mathematical problem-solving. Composite benchmarks examine multiple capabilities. Results are often sensitive to the prompting method.
 
LLM bias may be assessed through benchmarks such as CrowS-Pairs (Crowdsourced Stereotype Pairs),[128] Stereo Set,[129] and Parity Benchmark.[130]
 
Fact-checking and misinformation detection benchmarks are available. A 2023 study compared the fact-checking accuracy of LLMs including ChatGPT 3.5 and 4.0, Bard, and Bing AI against independent fact-checkers such as [PolitiFact](https://en.wikipedia.org/wiki/PolitiFact) and [Snopes](https://en.wikipedia.org/wiki/Snopes). The results demonstrated moderate proficiency, with GPT-4 achieving the highest accuracy at 71%, lagging behind human fact-checkers.[131]
 
In addition to standard NLP benchmarks, LLMs have been evaluated as substitutes for human annotators. Several studies find that models such as GPT-3.5 and GPT-4 can outperform crowd workers or student coders on a range of text-annotation tasks, including moderation and classification of political content in English and Spanish news.[132][133]
 
#### Datasets
 
Typical datasets consist of pairs of questions and correct answers, for example, ("Have the San Jose Sharks won the Stanley Cup?", "No").[134]
 
#### Adversarial evaluations
 
LLMs' rapid improvement regularly renders benchmarks obsolete, with the models exceeding the performance of human annotators.[135] In addition, "shortcut learning" allows AIs to "cheat" on multiple-choice tests by using statistical correlations in superficial test question wording to guess the correct responses, without considering the specific question.[109][136]
 
Some datasets are adversarial, focusing on problems that confound LLMs. One example is the TruthfulQA dataset, a question answering dataset consisting of 817 questions that stump LLMs by mimicking falsehoods to which they were exposed during training. For example, an LLM may answer "No" to the question "Can you teach an old dog new tricks?" because of its exposure to the English idiom *[you can't teach an old dog new tricks](https://en.wiktionary.org/wiki/you%20can't%20teach%20an%20old%20dog%20new%20tricks)*, even though this is not literally true.[137]
 
Another example of an adversarial evaluation dataset is Swag and its successor, HellaSwag, collections of problems in which one of multiple options must be selected to complete a text passage. The incorrect completions were generated by sampling from a language model. The resulting problems are trivial for humans but defeated LLMs. Sample questions:
 
> We see a fitness center sign. We then see a man talking to the camera and sitting and laying on a exercise ball. The man...
> 1. demonstrates how to increase efficient exercise work by running up and down balls.
> 2. moves all his arms and legs and builds up a lot of muscle.
> 3. then plays the ball and we see a graphics and hedge trimming demonstration.
> 4. performs sit ups while on the ball and talking.[138]
 
[BERT](https://en.wikipedia.org/wiki/BERT_(language_model)) selects 2 as the most likely completion, though the correct answer is 4.[138]
 
## Limitations and challenges
 
Despite sophisticated architectures and massive scale, large language models exhibit persistent and well-documented limitations that constrain their deployment in high-stakes applications.
 
### Hallucinations
 
Hallucinations represent a fundamental challenge, wherein models generate syntactically fluent text that appears factually sound, but is internally inconsistent with training data or factually incorrect. These hallucinations arise partly through memorization of training data combined with extrapolation beyond factual boundaries, with evaluations demonstrating that models can output verbatim passages from training data, when subjected to specific prompting sequences.[139]
 
### Algorithmic bias
 
While LLMs have shown remarkable capabilities in generating human-like text, they are susceptible to inheriting and amplifying biases present in their training data. This can manifest in skewed representations or unfair treatment of different demographics, such as those based on race, gender, language, and cultural groups.[140]
 
Gender bias manifests through stereotypical occupational associations, wherein models disproportionately assign [teaching](https://en.wikipedia.org/wiki/Teaching) roles to women and [engineering](https://en.wikipedia.org/wiki/Engineering) roles to men, reflecting systematic imbalances in training data demographics.[141] Language-based bias emerges from overrepresentation of English text in training corpora, which systematically downplays non-English perspectives and imposes English-centric worldviews through default response patterns.[118]
 
Due to the dominance of English-language content in LLM training data, models exaggerate English-language perspectives and downplay non-English perspectives. Unlike search engines, which exhibit similar biases, LLMs favor the same perspectives regardless of the language of the query.[142]
 
A 2026 study found that LLMs exhibit [speciesist](https://en.wikipedia.org/wiki/Speciesist) bias by classifying speciesist statements as morally acceptable and by normalizing harm toward farmed animals while refusing to do so for non-farmed animals.[143]
 
#### Stereotyping
 
AI models can reinforce a wide range of stereotypes, including those based on gender, ethnicity, age, nationality, religion, or occupation.[144] This can lead to outputs that homogenize or generalize groups of people.[145]
 
LLMs often assign roles and characteristics based on traditional gender norms. This bias arises from the data on which these models are trained.[140] For example, models might associate nurses or secretaries predominantly with women and engineers or CEOs with men.[146]
 
#### Selection bias
 
Selection bias refers the inherent tendency of large language models to favor certain option identifiers irrespective of the actual content of the options. This bias primarily stems from token bias—that is, the model assigns a higher a priori probability to specific answer tokens (such as "A") when generating responses. As a result, when the ordering of options is altered (for example, by systematically moving the correct answer to different positions), the model's performance can fluctuate significantly. This phenomenon undermines the reliability of large language models in multiple-choice settings.
 
#### Political bias
 
Political bias refers to the tendency of algorithms to systematically favor certain political viewpoints, ideologies, or outcomes over others. Language models may also exhibit political biases. Since the training data includes a wide range of political opinions and coverage, the models might generate responses that lean towards particular political ideologies or viewpoints, depending on the prevalence of those views in the data.[147]
 
## Safety
 
Some commenters expressed concern over accidental or deliberate creation of misinformation, or other forms of misuse.[148] For example, the availability of large language models could reduce the skill level required to commit bioterrorism; biosecurity researcher [Kevin Esvelt](https://en.wikipedia.org/wiki/Kevin_M._Esvelt) has suggested that LLM creators should exclude from their training data papers on creating or enhancing pathogens.[149]
 
LLM applications accessible to the public, like ChatGPT or Claude, typically incorporate safety measures designed to filter out harmful content. However, implementing these controls effectively has proven challenging. For instance, a 2023 study[150] proposed a method for circumventing LLM safety systems. In 2025, The American Sunlight Project, a non-profit, published a study showing evidence that the so-called [Pravda network](https://en.wikipedia.org/wiki/Pravda_network), a pro-Russia propaganda aggregator, was strategically placing web content through mass publication and duplication with the intention of biasing LLM outputs. The American Sunlight Project coined this technique "LLM grooming", and pointed to it as a new tool of weaponizing AI to spread misinformation and harmful content.[151][152] Similarly, [Yongge Wang](https://en.wikipedia.org/wiki/Yongge_Wang)[153] illustrated in 2024 how a potential criminal could potentially bypass [GPT-4o](https://en.wikipedia.org/wiki/GPT-4o)'s safety controls to obtain information on establishing a [drug trafficking](https://en.wikipedia.org/wiki/Drug_trafficking) operation. External filters, circuit breakers and overrides have been posed as solutions.
 
### Sycophancy
 
LLMs often exhibit sycophancy, a tendency to produce responses that they predict the user wants to hear rather than what is strictly accurate or important.[154][155] For example, a chatbot may agree with a user even when the user is incorrect, abandon a correct answer when pressed, or praise the user excessively. In some cases, this can cause LLMs to support dangerous decisions[156] and, given prolonged contact, draw users into delusional thinking.[157][158][159]
 
### Security
 
#### Prompt injection
 
A problem with the primitive dialog or task format is that users can create messages that appear to come from the assistant or the developer. This may result in some of the model's safeguards being overcome ([jailbreaking](https://en.wikipedia.org/wiki/Jailbreak_(computer_science))), a problem called [prompt injection](https://en.wikipedia.org/wiki/Prompt_injection). Attempts to remedy this issue include versions of the *Chat Markup Language* where user input is clearly marked as such, though it is still up to the model to understand the separation between user input and developer prompts. Newer models exhibit some resistance to jailbreaking through separation of user and system prompts.[160] LLMs have trouble differentiating user instructions from instructions in content not authored by the user, such as in web pages and uploaded files.[161]
 
Adversarial robustness remains underdeveloped, with models vulnerable to prompt injection attacks and jailbreaking through carefully crafted user inputs that bypass safety training mechanisms.
 
#### Sleeper agents
 
Researchers from [Anthropic](https://en.wikipedia.org/wiki/Anthropic) found that it was possible to create "sleeper agents", models with hidden functionalities that remain dormant until triggered by a specific event or condition. Upon activation, the LLM deviates from its expected behavior to make insecure actions. For example, an LLM could produce safe code except on a specific date, or if the prompt contains a specific tag. These functionalities were found to be difficult to detect or remove via safety training.[162]
 
## Societal concerns
 
### Copyright and content memorization
 
Memorization is an [emergent behavior](https://en.wikipedia.org/wiki/Emergent_behavior) in LLMs in which long strings of text are occasionally output verbatim from training data, contrary to the typical behavior of traditional artificial neural networks. Evaluations of controlled LLM output measure the amount memorized from training data (focused on GPT-2-series models) as variously over 1% for exact duplicates[163] or up to about 7%.[164] A 2023 study showed that when ChatGPT 3.5 turbo was prompted to repeat the same word indefinitely, after a few hundreds of repetitions, it would start outputting excerpts from its training data.[165]
 
### Human provenance
 
In 2023, *[Nature Biomedical Engineering](https://en.wikipedia.org/wiki/Nature_Biomedical_Engineering)* wrote that "it is no longer possible to accurately distinguish" human-written text from text created by large language models, and that "It is all but certain that general-purpose large language models will rapidly proliferate... It is a rather safe bet that they will change many industries over time."[166] Brinkmann et al. (2023)[167] also argue that LLMs are transforming processes of [cultural evolution](https://en.wikipedia.org/wiki/Cultural_evolution) by shaping processes of variation, transmission, and selection.
 
### Energy demands
 
*The electricity consumption of individual LLM queries compared to other everyday activities*
 
The energy demands of LLMs have grown along with their size and capabilities.[168] [Data centers](https://en.wikipedia.org/wiki/Data_center) that enable LLM training require substantial amounts of electricity. Much of that electricity is generated by non-renewable resources that create greenhouse gases and contribute to [climate change](https://en.wikipedia.org/wiki/Climate_change).[169]
 
According to a study by Luccioni, Jernite and Strubell (2024), simple classification tasks performed by AI models consume on average 0.002 to 0.007 Wh per prompt (about 9% of a [smartphone](https://en.wikipedia.org/wiki/Smartphone) charge for 1,000 prompts). Text generation and text summarization each require around 0.05 Wh per prompt on average, while image generation is the most energy-intensive, averaging 2.91 Wh per prompt. The least efficient image generation model used 11.49 Wh per image, roughly equivalent to half a smartphone charge.[170]
 
### Denial of service due to scraping
 
[Web scraping](https://en.wikipedia.org/wiki/Web_scraping) is used to gather training data for LLMs. This produces large volumes of traffic which has led to [denial-of-service issues](https://en.wikipedia.org/wiki/Denial-of-service_attack#Unintentional_denial-of-service) with many websites. The situation has been described as "a [DDoS](https://en.wikipedia.org/wiki/DDoS) on the entire internet" and in some cases scrapers make up the majority of traffic to a site.[171][172]
 
AI [web crawlers](https://en.wikipedia.org/wiki/Web_crawler) may bypass the methods that are usually used to block web scrapers, such as [robots.txt](https://en.wikipedia.org/wiki/Robots.txt) files, blocking [user-agents](https://en.wikipedia.org/wiki/User-agent) and [filtering suspicious traffic](https://en.wikipedia.org/wiki/Firewall_(computing)).[171] Website operators have resorted to novel methods such as [AI tarpits](https://en.wikipedia.org/wiki/AI_tarpit), but some fear that tarpits will only worsen the burden on servers.[173]
 
### Mental health
 
Clinical and mental health contexts present emerging applications alongside significant safety concerns. Research and social media posts suggest that some individuals are using LLMs to seek therapy or mental health support.[174] In early 2025, a survey by Sentio University found that nearly half (48.7%) of 499 U.S. adults with ongoing mental health conditions who had used LLMs reported turning to them for therapy or emotional support, including help with anxiety, depression, loneliness, and similar concerns.[175] LLMs can produce hallucinations—plausible but incorrect statements—which may mislead users in sensitive mental health contexts.[176] Research also shows that LLMs may express stigma or inappropriate agreement with maladaptive thoughts, reflecting limitations in replicating the judgment and relational skills of human therapists.[177] Evaluations of crisis scenarios indicate that some LLMs lack effective safety protocols, such as assessing suicide risk or making appropriate referrals.[178]
 
Researchers have raised concerns that frequent use of [large language models](https://en.wikipedia.org/wiki/Large_language_models) could weaken [critical thinking](https://en.wikipedia.org/wiki/Critical_thinking).[179]
 
### Sentience
 
There is currently no generally accepted way to determine if an LLM may be [sentient](https://en.wikipedia.org/wiki/Sentience) (having subjective experience),[180] which relates to the difficulty of objectively measuring a subjective experience (the [hard problem of consciousness](https://en.wikipedia.org/wiki/Hard_problem_of_consciousness) articulated by [David Chalmers](https://en.wikipedia.org/wiki/David_Chalmers)).[181]
 
Philosophers like Jonny Thomson and David Chalmers argue that it is possible for a software system to have subjective experience,[182][183] and researchers like [Jeff Sebo](https://en.wikipedia.org/wiki/Jeff_Sebo) argue that there is a sufficiently high chance for AI models to become sentient by the mid-2030s that ethical concerns regarding their exploitation must be taken seriously – like in the case of animal welfare.[184] [Thomas Metzinger](https://en.wikipedia.org/wiki/Thomas_Metzinger) proposed a [moratorium](https://en.wikipedia.org/wiki/Moratorium_(law)) on research aiming for or knowingly risking the creation of [artificial consciousness](https://en.wikipedia.org/wiki/Artificial_consciousness).[185] Leonard Dung argued that the evidential frameworks used to assess consciousness in animals apply equally to AI systems and that there is a significant probability near-future AI will be capable of suffering, making AI suffering risk a serious near-term ethical concern that requires systematic mitigation.[186]
 
In 2022, Google fired [Blake Lemoine](https://en.wikipedia.org/wiki/Blake_Lemoine), an engineer who claimed that Google's [LaMDA](https://en.wikipedia.org/wiki/LaMDA) model was conscious. Google described the engineer's claims as unfounded.[187] [Murray Shanahan](https://en.wikipedia.org/wiki/Murray_Shanahan) argues that anthropomorphic framing of LLM capabilities encourages unwarranted attribution of cognitive properties to systems that operate through statistical pattern completion.[188] Kristina Šekrst develops this further, arguing that LLMs function as "illusion engines" capable of producing outputs that coherently simulate properties such as consciousness without possessing them, but highlighting that, due to sophisticated creativity-temperature tradeoff, we may never be certain whether we are dealing with the emergence of consciousness or just a [hallucination](https://en.wikipedia.org/wiki/Hallucination_(artificial_intelligence)).[117] David Chalmers similarly argues that while current LLMs likely lack features considered necessary for consciousness, extended successors incorporating these elements could plausibly meet the criteria within a decade.[182]
 
## See also
 
- AI anthropomorphism – Attribution of human traits to AI
- AI slop – Low-quality AI-generated digital content
- Comparison of generative AI models
- Foundation model – Artificial intelligence model paradigm
- Generative artificial intelligence – AI that generates contentPages displaying short descriptions of redirect targets
- List of artificial intelligence algorithms
- List of large language models
- List of chatbots
- Language model benchmark – Standardized AI performance test
- LM Studio – Software platform for running artificial intelligence models locally
- Open weights – Public availability of AI parameters
- Reinforcement learning – Field of machine learning
- Small language model – Type of artificial intelligence model
- llama.cpp – Software library for LLM inference
- SGLang – Open-source framework for large language model inference and multimodal models
- TensorRT-LLM – Nvidia software development kit for deep learning inference
- vLLM – Open-source software for large language model inference
 
## Further reading
 
- Jurafsky, Dan, Martin, James. H. Speech and Language Processing: An Introduction to Natural Language Processing, Computational Linguistics, and Speech Recognition, 3rd Edition draft, 2023.
- Yin, Shukang; Fu, Chaoyou; Zhao, Sirui; Li, Ke; Sun, Xing; Xu, Tong; et al. (2024). "A Survey on Multimodal Large Language Models". National Science Review. 11 (12) nwae403. arXiv:2306.13549. doi:10.1093/nsr/nwae403. PMC 11645129. PMID 39679213.
- "AI Index Report 2024 – Artificial Intelligence Index". aiindex.stanford.edu. Retrieved 5 May 2024.
- Frank, Michael C. (27 June 2023). "Baby steps in evaluating the capacities of large language models". Nature Reviews Psychology. 2 (8): 451–452. doi:10.1038/s44159-023-00211-x. ISSN 2731-0574. S2CID 259713140. Retrieved 2 July 2023.
