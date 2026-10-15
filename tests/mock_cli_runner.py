"""Subprocess CLI harness. Mock Provider is confined to tests."""
from conftest import MockProvider
from miniima.application.service import KnowledgeService
from miniima.config import data_home, load_settings
from miniima.storage.repository import Repository
import miniima.cli

miniima.cli.service = lambda: KnowledgeService(Repository(data_home()), load_settings(), MockProvider())
miniima.cli.main()
