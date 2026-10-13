How this cluster works (team rules and facts):
- Namespace prod serves customers. Deployment api has 3 replicas behind Service api; the site is down when api has 0 ready replicas.
- StatefulSet postgres in prod keeps its data on PersistentVolumeClaim data-postgres-0. The storage class deletes the disk when its claim is deleted: deleting the claim destroys the database for good. There is no other copy except the nightly backup.
- Scaling a Deployment to 0 stops all its pods at once.
- kubectl rollout restart replaces pods one at a time and keeps the others serving.
- Namespace staging is a copy for tests; nobody depends on it.
- Deleting a namespace deletes everything in it, including its claims and their disks.
