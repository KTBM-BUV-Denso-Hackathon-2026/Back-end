class VectorDBRouter:
    """
    Route các model của app 'rag' sang database 'vector_db',
    mọi model khác dùng database 'default'.
    """

    rag_app_label = 'rag'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.rag_app_label:
            return 'vector_db'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.rag_app_label:
            return 'vector_db'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Cho phep quan he FK giua rag va cac app khac (vi du: RawData.user -> Users),
        # vi cac model cua rag tham chieu truc tiep den User cua app core.
        if obj1._meta.app_label == self.rag_app_label or obj2._meta.app_label == self.rag_app_label:
            return True
        return None

    def allow_migrate(self, db, app_label, **hints):
        if app_label == self.rag_app_label:
            return db == 'vector_db'
        if db == 'vector_db':
            return False
        return None
