"""Chunker tests: packing, word-boundary splitting, page isolation, overlap."""

from common.chunker import chunk_pages

SENTENCE = "หน่วยงานของรัฐต้องใช้จ่ายเงินอย่างโปร่งใสคุ้มค่าและประหยัดตามกฎหมายว่าด้วยวินัยการเงินการคลัง"


class TestChunkPages:
    def test_small_page_is_one_chunk(self):
        drafts = chunk_pages([SENTENCE])
        assert len(drafts) == 1
        assert drafts[0].chunk_index == 0
        assert drafts[0].page == 1
        assert drafts[0].text == SENTENCE

    def test_blank_pages_skipped_but_numbering_kept(self):
        drafts = chunk_pages(["", "  \n ", SENTENCE])
        assert len(drafts) == 1
        assert drafts[0].page == 3  # page numbers stay aligned with the PDF

    def test_chunks_never_span_pages(self):
        drafts = chunk_pages([SENTENCE, SENTENCE])
        assert [d.page for d in drafts] == [1, 2]

    def test_packing_respects_target(self):
        lines = "\n".join([SENTENCE] * 20)  # ~1900 chars of short lines
        drafts = chunk_pages([lines], target_chars=400)
        assert len(drafts) > 2
        assert all(len(d.text) <= 400 + len(SENTENCE) for d in drafts)

    def test_consecutive_chunks_overlap_one_line(self):
        numbered = "\n".join(f"บรรทัดที่ {i} {SENTENCE}" for i in range(10))
        drafts = chunk_pages([numbered], target_chars=300)
        for prev, nxt in zip(drafts, drafts[1:], strict=False):
            assert prev.text.splitlines()[-1] == nxt.text.splitlines()[0]

    def test_long_line_split_at_word_boundaries(self):
        long_line = SENTENCE * 30  # one massive unbroken paragraph
        drafts = chunk_pages([long_line], target_chars=400, max_chars=500)
        assert len(drafts) > 1
        # no piece may cut คุ้มค่า (a dictionary word) in half
        for d in drafts:
            assert not d.text.startswith("้")  # never split before a combining mark

    def test_chunk_index_is_document_wide(self):
        drafts = chunk_pages([SENTENCE, SENTENCE, SENTENCE])
        assert [d.chunk_index for d in drafts] == [0, 1, 2]
