/*
 * unity_lmdb_dump.c
 * Dump a single sub-database from an LMDB env as hex key/value pairs.
 *
 * Usage:
 *   unity_lmdb_dump <env-path> <subdb-name>
 *
 * Output format (one entry per line, two lines per entry):
 *   K <hex-key>
 *   V <hex-value>
 *
 * Opens the env read-only with MDB_NOSUBDIR (Unity uses single-file LMDB)
 * and MDB_NOLOCK (so a live Unity Editor doesn't block us).
 *
 * Build (MSVC, x64):
 *   cl /nologo /O2 /MT /W2 /D_CRT_SECURE_NO_WARNINGS /Fe:unity_lmdb_dump.exe ^
 *      unity_lmdb_dump.c "<LMDB>/mdb.c" "<LMDB>/midl.c" ^
 *      ntdll.lib advapi32.lib /link /INCREMENTAL:NO
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lmdb.h"

static void hex_print(FILE* fp, const unsigned char* buf, size_t n)
{
    static const char* hexd = "0123456789abcdef";
    for (size_t i = 0; i < n; ++i) {
        fputc(hexd[buf[i] >> 4], fp);
        fputc(hexd[buf[i] & 0xF], fp);
    }
}

static int die(const char* what, int rc)
{
    fprintf(stderr, "%s: %s (%d)\n", what, mdb_strerror(rc), rc);
    return 2;
}

int main(int argc, char** argv)
{
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <env-file> <subdb-name>\n", argv[0]);
        return 1;
    }

    const char* env_path = argv[1];
    const char* subdb    = argv[2];

    MDB_env* env;
    int rc = mdb_env_create(&env);
    if (rc) return die("mdb_env_create", rc);

    /* Unity uses many sub-DBs in one env */
    rc = mdb_env_set_maxdbs(env, 64);
    if (rc) { mdb_env_close(env); return die("mdb_env_set_maxdbs", rc); }

    /* MDB_NOSUBDIR: env is a single file, not a dir.
     * MDB_RDONLY:   read-only.
     * MDB_NOLOCK:   don't take a write lock; safe alongside a live Editor reader. */
    rc = mdb_env_open(env, env_path, MDB_NOSUBDIR | MDB_RDONLY | MDB_NOLOCK, 0);
    if (rc) { mdb_env_close(env); return die("mdb_env_open", rc); }

    MDB_txn* txn;
    rc = mdb_txn_begin(env, NULL, MDB_RDONLY, &txn);
    if (rc) { mdb_env_close(env); return die("mdb_txn_begin", rc); }

    MDB_dbi dbi;
    rc = mdb_dbi_open(txn, subdb, 0, &dbi);
    if (rc) {
        mdb_txn_abort(txn);
        mdb_env_close(env);
        return die("mdb_dbi_open", rc);
    }

    MDB_cursor* cur;
    rc = mdb_cursor_open(txn, dbi, &cur);
    if (rc) {
        mdb_txn_abort(txn);
        mdb_env_close(env);
        return die("mdb_cursor_open", rc);
    }

    MDB_val key, val;
    long count = 0;
    while ((rc = mdb_cursor_get(cur, &key, &val, MDB_NEXT)) == 0) {
        fputc('K', stdout); fputc(' ', stdout);
        hex_print(stdout, (const unsigned char*)key.mv_data, key.mv_size);
        fputc('\n', stdout);
        fputc('V', stdout); fputc(' ', stdout);
        hex_print(stdout, (const unsigned char*)val.mv_data, val.mv_size);
        fputc('\n', stdout);
        ++count;
    }
    if (rc != MDB_NOTFOUND) {
        fprintf(stderr, "mdb_cursor_get: %s (%d)\n", mdb_strerror(rc), rc);
    }
    fprintf(stderr, "Dumped %ld entries from sub-db '%s'\n", count, subdb);

    mdb_cursor_close(cur);
    mdb_txn_abort(txn);
    mdb_env_close(env);
    return 0;
}
