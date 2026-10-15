import type { DocumentRecord, Source } from './types';

// Explicit development fixture for comparing the supplied RAG screenshot.
// The production bridge never calls this module's fixture.
export const referenceDocuments: DocumentRecord[] = [
  { id: 'rag-paper', filename: 'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.md', status: 'ready', error: null, chunk_count: 16, source_type: 'markdown', created_at: '2026-10-14T14:23:00' },
  { id: 'rag-review', filename: '大语言模型综述与应用进展.md', status: 'ready', error: null, chunk_count: 12, source_type: 'markdown', created_at: '2026-10-13T20:11:00' },
  { id: 'rag-notes', filename: 'RAG 技术笔记.txt', status: 'ready', error: null, chunk_count: 8, source_type: 'txt', created_at: '2026-10-13T16:08:00' },
];

export const referenceSources: Source[] = [
  { id: 101, document_id: 'rag-paper', filename: referenceDocuments[0].filename, citation_number: 1, score: .92,
    source_metadata: { line_start: 3, line_end: 16, heading_path: ['RAG 的基本思想与优势'] },
    content: '### 3　RETRIEVAL-AUGMENTED GENERATION\n\nWe combine a pre-trained parametric memory with a non-parametric memory, which we query with the input sequence x to produce a set of relevant documents z = (z₁, …, zₖ) from a large corpus (e.g., Wikipedia). The retrieved documents are then used as additional context for generation, allowing the model to produce more accurate and grounded responses.\n\n**Retrieval provides relevant external evidence for answer generation, which significantly reduces factual errors and hallucinations in large language models.**\n\nThe retrieved evidence is included in the context of the answer. Readers can inspect each source passage and compare the generated response with the original material.' },
  { id: 102, document_id: 'rag-review', filename: referenceDocuments[1].filename, citation_number: 2, score: .86,
    source_metadata: { line_start: 22, line_end: 35, heading_path: ['实验结果分析'] },
    content: '### 实验结果分析\n\n检索增强生成通过引入相关外部证据，为语言模型提供可核对的事实依据。检索质量、文档时效性和来源可信度都会影响最终回答。\n\n使用引用可帮助读者确认答案是否准确反映了文档原文。' },
  { id: 103, document_id: 'rag-notes', filename: referenceDocuments[2].filename, citation_number: 3, score: .78,
    source_metadata: { line_start: 38, line_end: 49, heading_path: ['与其他方法的对比'] },
    content: 'RAG 技术笔记：降低大模型幻觉的有效方法\n\n相比只依赖模型记忆的回答，RAG 可通过更新知识库获得较新的资料。回答应标注真实来源，并为用户保留逐段核对原文的入口。' },
];

export const referenceAnswer = `RAG（Retrieval-Augmented Generation，检索增强生成）是一种将外部知识检索和大语言模型生成相结合的技术。它通过从知识库中检索与问题相关的文档片段，再将这些信息作为上下文提供给模型，从而生成更准确、可追溯的回答。

RAG 降低大语言模型幻觉的主要原因包括：

1. **提供真实的外部证据**  
   模型在生成回答时基于检索到的文档内容，而不是仅依赖自身的参数记忆。
2. **缩小生成范围**  
   通过检索相关信息，模型的回答更聚焦于具体事实，减少自由发挥的空间。
3. **支持引用溯源**  
   生成的内容可以直接引用原始文档，方便验证和追踪，提高可信度。
4. **动态更新知识**  
   无需重新训练模型，只需更新知识库即可获得最新的信息。

因此，RAG 能够显著减少事实性错误，让大语言模型在专业领域中的回答更加可靠。`;
